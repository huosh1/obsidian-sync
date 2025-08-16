# Obsidian Vault Manager

A comprehensive tool to automatically sync your Obsidian vault with Dropbox. Features a clean Apple-style interface with intelligent synchronization, file deletion management, and real-time monitoring.
Big advantage is that .obsidian with all themes, community plugins are in this folder. Then, when you sync on another desktop, you will have all your differents plugins.

## What it does

This application provides seamless bidirectional synchronization between your local Obsidian vault and Dropbox. It monitors your files for changes, automatically detects what needs to be synchronized, and keeps everything in sync without duplicating unchanged files. The app now includes intelligent deletion handling to prevent accidentally restored files and provides granular control over file operations.

### Key Features

- **Smart Synchronization**: Only syncs changed files, saving time and bandwidth
- **Deletion Management**: Detects locally deleted files and asks for confirmation before removing them from cloud
- **Real-time Monitoring**: Instantly syncs changes as you work
- **File Restoration**: Easily restore accidentally deleted files from cloud backup
- **Snapshot Creation**: Create timestamped backups of your entire vault
- **Direct Obsidian Launch**: Start Obsidian with your vault directly from the app
- **Cross-platform**: Works on Windows, macOS, and Linux

## Installation

### Installing Python

**Windows users** should download Python from the official website at python.org. During installation, make sure to check the "Add Python to PATH" option. This allows you to run Python commands from any folder.

**macOS users** can use Homebrew: `brew install python3` or download from python.org.

**Linux users** can install via package manager: `sudo apt install python3 python3-pip` (Ubuntu/Debian) or equivalent.

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
- `files.metadata.read`

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

### Initial Setup

When the app opens:

1. **Select your vault folder**: Use the "Search" button to select your Obsidian vault folder (where your `.obsidian` folder is located)
2. **Initialize file tracking**: Click "📁 Init Tracking" to register all existing files in the database
3. **Check connection**: The status bar should show "Connected" with your Dropbox account name

The app will remember your settings for future use.

### Synchronization Options

**Automatic Synchronization**: Runs a complete sync every 30 minutes (configurable). Enable this for regular background syncing.

**Real-time Synchronization**: Watches for file changes and uploads them immediately. Perfect for instant backup as you work.

**Auto-confirm file deletions**: When enabled, automatically removes files from cloud when deleted locally. When disabled, shows confirmation dialog.

### Main Operations

**Synchronize**: Performs a complete two-way sync, handling file changes, additions, and deletions intelligently.

**Start Obsidian**: Launches Obsidian directly with your configured vault.

**Push Local**: Uploads only your local changes to Dropbox.

**Pull Remote**: Downloads only changes from Dropbox to your local vault.

**Snapshot**: Creates a timestamped ZIP backup of your entire vault in Dropbox.

### File Deletion Management

**🗑️ Check Deletions**: Manually check for files that have been deleted locally. Shows a confirmation dialog where you can:
- **Delete**: Remove files permanently from cloud storage
- **Restore**: Download files back to your local vault
- **Cancel**: Do nothing and keep files in pending state

**📁 Init Tracking**: Initialize file tracking for existing files. Use this once when setting up the app or when adding the vault to a new device.

## Advanced Features

### Deletion Workflow

When you delete files from your vault:

1. The app detects the deletion during the next sync or file check
2. Deleted files are marked as "pending deletion" in the database
3. A confirmation dialog appears with options to permanently delete or restore files
4. You can selectively choose which files to delete or restore
5. Auto-confirmation mode bypasses the dialog for streamlined workflow

### File Filtering

The app automatically ignores certain files and patterns:
- Temporary files (`*.tmp`, `*.bak`)
- System files (`.DS_Store`, `Thumbs.db`)
- Obsidian workspace files (`.obsidian/workspace*`)
- Trash folder contents (`.trash/*`)
- Files with problematic characters or names

### Path Sanitization

File paths are automatically cleaned for Dropbox compatibility:
- Converts Windows backslashes to forward slashes
- Removes problematic Unicode characters
- Handles special characters in filenames
- Maintains file integrity across different operating systems

## Troubleshooting

### Common Issues

**Files not syncing**: Check your Dropbox connection status and ensure you have sufficient storage space.

**Deletions not detected**: Run "📁 Init Tracking" first to register existing files, then use "🗑️ Check Deletions".

**Permission errors**: Ensure your Dropbox app has the correct permissions enabled.

**Path issues**: The app automatically handles most path problems, but very long filenames (>255 characters) may be skipped.

### Log Files

Check these files for detailed information:
- `vault_manager.log` - Application log with sync details
- `vault_manager.db` - SQLite database with file metadata and history
- `vault_config.json` - Configuration settings

### Reset Options

To reset the application:
1. Delete `vault_config.json` to reset settings
2. Delete `vault_manager.db` to reset file tracking (requires re-initialization)
3. Delete `vault_manager.log` to clear log history

## File Organization

The application creates several files in its directory:
- `vault_config.json` - Stores your vault path and sync settings
- `vault_manager.db` - SQLite database for sync history, file metadata, and deletion tracking
- `vault_manager.log` - Detailed log file for troubleshooting and monitoring

These files are automatically created and managed by the application.

## Tips for Best Experience

1. **First-time setup**: Always run "📁 Init Tracking" before using deletion detection
2. **Regular backups**: Use the "Snapshot" feature before major vault reorganizations
3. **Sync before major changes**: Run a full sync before moving or deleting many files
4. **Monitor logs**: Check the log panel for any sync issues or conflicts
5. **Test deletion workflow**: Try deleting a test file first to understand the confirmation process

## Version History

### v2.0 - Enhanced Deletion Management
- Added intelligent file deletion detection and confirmation
- Implemented file restoration capabilities
- Enhanced database schema with deletion tracking
- Improved path handling and sanitization
- Added manual tracking initialization
- Better real-time file monitoring

### v1.0 - Initial Release
- Basic bidirectional synchronization
- Real-time file watching
- Snapshot creation
- Direct Obsidian launching
