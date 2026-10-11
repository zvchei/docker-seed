# acli

Atlassian CLI. Config and keyrings persist on volumes.

## Use

```bash
ds run acli                                  # interactive bash
ds shell acli acli jira auth login --web     # once
ds shell acli acli jira workitem search --jql "assignee = currentUser()"
```
