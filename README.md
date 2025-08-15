# Obsidian Vault Manager

A simple tool to automatically sync your Obsidian vault with Dropbox. Features a clean Apple-style interface with intelligent synchronization that only uploads/downloads changed files.

## What it does

This application provides seamless synchronization between your local Obsidian vault and Dropbox. It monitors your files for changes, automatically detects what needs to be synchronized, and keeps everything in sync without duplicating unchanged files. You can also launch Obsidian directly from the app and create snapshots of your vault.

## Installation

### Installing Python

**Windows users** should download Python from the official website at python.org. During installation, make sure to check the "Add Python to PATH" option. This allows you to run Python commands from any folder.

```

### Installing Dependencies

Once Python is installed, you need to install the required packages. Open a terminal (or Command Prompt on Windows) and run:

```bash
pip install customtkinter dropbox schedule watchdog
```

If you encounter permission errors on Linux, you might need to use `pip3` instead of `pip`, or add `--user` flag:

```bash
pip3 install --user customtkinter dropbox schedule watchdog
```

### Getting the Application

Download the `obsidian_vault_manager.py` file and place it in a dedicated folder like `ObsidianSync`. This keeps everything organized and makes it easy to find later.

## Dropbox Setup

### Creating a Dropbox App

You need to create a Dropbox application to get API access. Go to the Dropbox App Console at dropbox.com/developers/apps and click "Create app". Choose "Scoped access" and "Full Dropbox" access type. Give your app a name like "ObsidianSync" or whatever you prefer.

### Configuring Permissions

In your newly created app settings, go to the Permissions tab and enable these permissions:
- `files.metadata.write`
- `files.content.write` 
- `files.content.read`

These permissions allow the app to read, write, and manage your files on Dropbox.

### Getting Your Credentials

In the Settings tab of your Dropbox app, you'll find your App key and App secret. Copy these values as you'll need them in the next step.

### Generating a Refresh Token

To get a refresh token that never expires, you need to go through Dropbox's OAuth flow. The easiest way is to use this simple Python script:

```python
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect

# Replace with your app credentials
APP_KEY = "your_app_key_here"
APP_SECRET = "your_app_secret_here"

auth_flow = DropboxOAuth2FlowNoRedirect(APP_KEY, use_pkce=True, token_access_type='offline')

authorize_url = auth_flow.start()
print("1. Go to:", authorize_url)
print("2. Click 'Allow'")
print("3. Copy the authorization code")

auth_code = input("Enter authorization code: ").strip()

try:
    oauth_result = auth_flow.finish(auth_code)
    print(f"Refresh token: {oauth_result.refresh_token}")
except Exception as e:
    print(f"Error: {e}")
```

Save this as `get_token.py`, replace the APP_KEY and APP_SECRET with your values, then run it:

```bash
python get_token.py
```

Follow the instructions to get your refresh token.

### Updating the Application

Open `obsidian_vault_manager.py` and find the `DROPBOX_CONFIG` section near the top. Replace the placeholder values with your actual credentials:

```python
DROPBOX_CONFIG = {
    "app_key": "your_app_key_here",
    "app_secret": "your_app_secret_here", 
    "refresh_token": "your_refresh_token_here"
}
```

## Using the Application

### First Launch

Run the application by opening a terminal in the folder containing the script and typing:

```bash
python obsidian_vault_manager.py
```

On some Linux systems, you might need to use `python3` instead of `python`.

### Initial Setup

When the app opens, use the "Browse" button to select your Obsidian vault folder. This is typically where your `.obsidian` folder is located. The app will remember this location for future use.

The status bar at the bottom will show your Dropbox connection status. If everything is configured correctly, you should see "Connected" with your Dropbox account name.

### Synchronization Options

You have two automatic sync options available. "Automatic synchronization" runs a full sync every 30 minutes (configurable). "Real-time synchronization" watches for file changes and uploads them immediately. You can enable one or both depending on your needs.

### Manual Operations

The main "Synchronize" button performs a complete two-way sync, analyzing differences and updating files as needed. "Push Local" only uploads your local changes to Dropbox. "Pull Remote" only downloads changes from Dropbox. "Snapshot" creates a timestamped backup of your entire vault.

## Troubleshooting

If you get permission errors on Linux, try running with `python3` instead of `python`. Make sure all dependencies are installed correctly by running the pip install command again.

For Dropbox connection issues, verify your app credentials are correct and that you've enabled the required permissions in the Dropbox App Console.

If the interface doesn't appear, make sure you have `python3-tkinter` installed on Linux systems.

## File Organization

The application creates several files in its directory:
- `vault_config.json` - Stores your vault path and settings
- `vault_manager.db` - Database for sync history and file metadata  
- `vault_manager.log` - Log file for troubleshooting

These files are automatically created and managed by the application.
