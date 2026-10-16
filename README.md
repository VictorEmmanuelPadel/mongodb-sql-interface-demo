# MongoDB SQL Interface demo

This project prepares a Power BI demo of the [MongoDB SQL Interface](https://www.mongodb.com/docs/sql-interface/) on a dedicated Atlas cluster you already have. The cluster must be M10 or larger and run MongoDB 6.0 or later.

**Setup can take up to 30 minutes.** Most of that time is the Windows VM installing Power BI Desktop.

## Run

You need Python 3.11 or later, Terraform 1.6 or later, Project Owner on the Atlas project, and an Azure subscription that can create a Windows VM. `setup` installs the Atlas CLI and the Azure CLI and signs you in to both. On a Mac, it also installs Windows App, the Remote Desktop client. Before it changes anything, it reads the cluster and stops if the cluster is paused or cannot use the SQL Interface.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

From the repository root:

```bash
python -m sql_demo setup
```

When setup finishes, the terminal prints the VM address and the Power BI username, password, and URI.

On a Mac, **Windows App** has been automatically installed as part of the setup process. It is in the Applications folder. This is Microsoft's Remote Desktop client. Use that installed app to connect to the Windows VM.

Edit `.env` before you run setup. The first three values are required. The database should already contain a small amount of data.

| Variable | Required | Default | What it sets |
| --- | --- | --- | --- |
| `ATLAS_PROJECT_ID` | Yes | | Atlas project ID, 24 hex characters. `atlas projects list` shows it. |
| `ATLAS_CLUSTER_NAME` | Yes | | Existing dedicated cluster, M10 or larger, on MongoDB 6.0 or later. |
| `ATLAS_DATABASE` | Yes | `sample_mflix` | Database exposed to Power BI. Separate more than one name with commas. |
| `SQL_USERNAME` | | `sql-demo` | Atlas database user for the schema builder and Power BI. |
| `SQL_PASSWORD` | | Generated | Password for that database user. Blank generates one in `output/sql-password` and reuses it. |
| `VM_ADMIN_USERNAME` | | `sqlInterfaceDemo` | Local Windows account for Remote Desktop. 3–20 letters and digits. `admin`, `administrator`, `guest`, `root`, `user`, and `azure` are reserved. |
| `VM_ADMIN_PASSWORD` | | Generated | Windows password. Blank generates one in `output/vm-password` and reuses it. A password you set must be 12–123 characters and include three of lowercase, uppercase, digit, and symbol. |
| `AZURE_LOCATION` | | `eastus` | Azure region for the VM, such as `eastus` or `westus2`. |

## Connect

1. On a Mac, open the **Windows App** that setup installed. It is in the Applications folder.
2. Add a PC using the VM's public IP address printed at the end of setup.
3. Sign in with the Windows username and password printed there. Accept the certificate warning for the new VM if prompted.
4. On Windows, use the built-in Remote Desktop client (`mstsc`) with the same details.
5. Inside the VM, open **Power BI Desktop** from the desktop shortcut.
6. Choose **Get data**, search for **MongoDB**, and select **MongoDB Atlas SQL**.
7. Paste the MongoDB URI printed at the end of setup. Do not put a username or password in the URI.
8. Enter the database name and sign in as the database user printed there.
9. Load a collection.

## Remove the demo

The Azure VM is billed until you delete it. This command removes the VM, the demo database user, and the SQL Interface. It does not delete the Atlas cluster.

```bash
python -m sql_demo destroy --purge-atlas
```
