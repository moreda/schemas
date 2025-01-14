"""Rebuilds JSON Schemas from our models."""
import glob
import json
import multiprocessing
import os
import subprocess
from pathlib import Path
from typing import Dict, List

import requests
from rich.progress import Progress

from ansibleschemas.ansiblelint import AnsibleLintModel
from ansibleschemas.api import ansible_modules
from ansibleschemas.galaxy import GalaxyFileModel
from ansibleschemas.meta import MetaModel
from ansibleschemas.molecule import MoleculeScenarioModel
from ansibleschemas.playbook import PlaybookFileModel
from ansibleschemas.requirements import RequirementsFileModel
from ansibleschemas.tasks import TasksListModel
from ansibleschemas.vars import VarsModel

# Not really Ansible schemas, but included for convenience
from ansibleschemas.zuul import ZuulConfigModel

GALAXY_API_URL = "https://galaxy.ansible.com"
out_dir = Path(os.getcwd()) / "f"
module_dir = Path(__file__).resolve().parents[0]
GENERATED_HEADER = "# pylint: disable-all\n"


def dump_galaxy_platforms() -> None:
    """Dumps galaxy platforms into a python module."""
    filename = f"{module_dir}/_galaxy.py"
    print(f"Dumping list of Galaxy platforms to {filename}")
    platforms: Dict[str, List[str]] = {}
    result = {'next_link': '/api/v1/platforms/'}
    while result.get('next_link', None):
        url = GALAXY_API_URL + result['next_link']
        result = requests.get(url).json()
        for entry in result['results']:
            if not isinstance(entry, dict):
                continue
            name = entry.get('name', None)
            release = entry.get('release', None)
            if not name or not isinstance(name, str):
                continue
            if name and name not in platforms:
                platforms[name] = []
            if release not in ['any', 'None'] and release not in platforms[name]:
                platforms[name].append(release)

    with open(filename, "w") as file:
        file.write(GENERATED_HEADER + f"\nGALAXY_PLATFORMS = {platforms}\n")


def dump_module_doc(module):
    """Dumps module docs as json."""
    try:
        module_json = subprocess.check_output(["ansible-doc", "-j", module], universal_newlines=True)
        data = json.loads(module_json)
        # we remove filename from the dump as that prevents reproduceble builds as
        # they are full paths.
        data[module]["doc"].pop("filename", None)
        # removed as not being used by us (performance)
        data[module]["doc"].pop("author", None)
        data[module]["doc"].pop("notes", None)
        data[module]["doc"].pop("examples", None)
        data[module]["doc"].pop("return", None)

        with open(f"data/modules/{module}.json", "w") as file:
            file.write(json.dumps(data, indent=2, sort_keys=True))
            file.write("\n")
    except subprocess.CalledProcessError:
        print(f"Module {module} skipped as it failed to export documentation.")
    return module


def doc_dump() -> None:
    """Dump documentation for all Ansible modules."""
    files = glob.glob('data/modules/*.json')
    for file in files:
        os.remove(file)

    modules = list(ansible_modules())
    with Progress() as progress:
        results = []
        task_id = progress.add_task("Dumping doc for each module ...", total=len(modules))
        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            for result in pool.imap(dump_module_doc, modules):
                results.append(result)
                progress.advance(task_id)


def map_type(ansible_type: str) -> str:
    """Return JSON date type for a given Ansible type."""
    # https://json-schema.org/understanding-json-schema/reference/type.html
    # raw is used for file mode by ansible
    if ansible_type in ['str', 'filename', 'path', 'raw', 'sid']:
        return 'string'
    if ansible_type == 'list':
        return 'array'
    if ansible_type == 'bool':
        return 'boolean'
    if ansible_type == 'int':
        return 'integer'
    if ansible_type in ['dict', 'jsonarg', 'json']:
        return 'object'
    if ansible_type == 'float':
        return 'number'
    raise NotImplementedError(f"Unable to map ansible type {ansible_type} to JSON Schema type.")


def main() -> None:
    """Main entry point"""

    # dump_galaxy_platforms()

    schemas = {
        "ansible-lint": AnsibleLintModel,
        "galaxy": GalaxyFileModel,
        "meta": MetaModel,
        "molecule": MoleculeScenarioModel,
        "playbook": PlaybookFileModel,
        "requirements": RequirementsFileModel,
        "tasks": TasksListModel,
        "vars": VarsModel,
        "zuul": ZuulConfigModel,
    }
    schema_filenames = {
        "ansible-lint": "ansible-lint",
        "galaxy": "ansible-galaxy",
        "meta": "ansible-meta",
        "molecule": "molecule",
        "playbook": "ansible-playbook",
        "requirements": "ansible-requirements",
        "tasks": "ansible-tasks",
        "vars": "ansible-vars",
        "zuul": "zuul",
    }

    for schema, model in schemas.items():
        print(f"Building schema for {schema}")

        output_file = out_dir / f"{schema_filenames[schema]}.json"
        with open(output_file, "w") as file:
            file.write(model.schema_json(
                indent=2,
                sort_keys=True))
            # by_alias
            # skip_defaults
            # exclude_unset
            # exclude_defaults
            # exclude_none
            # include
            # exclude
            # encoder function, defaults to json.dumps()
            file.write("\n")


if __name__ == "__main__":
    main()
