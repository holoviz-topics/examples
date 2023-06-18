from dodo import (
    all_project_names,
    deployment_cmd_to_endpoint,
    project_spec,
)


def deployments_list():

    projects_local = all_project_names(root='')

    deployments_local = {}
    for project in projects_local:
        spec = project_spec(project)
        depls = spec['examples_config'].get('deployments', [])
        if depls:
            deployments_local[project] = depls

    return [
        deployment_cmd_to_endpoint(depl['command'], name, full=True)
        for name, depls in deployments_local.items()
        for depl in depls
    ]

def main():

    endpoints_local = deployments_list()

    with open('deployments.yaml', 'w') as f:
        for endpoint in endpoints_local:
            f.write(f'- {endpoint}\n')
        
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
