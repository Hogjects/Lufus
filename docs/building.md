# Building

## System Dependencies

Lufus requires these system packages for drive formatting operations:

**Arch/Manjaro:**
```bash
sudo pacman -S dosfstools exfatprogs udftools ntfs-3g e2fsprogs
```

**Debian/Ubuntu:**
```bash
sudo apt install dosfstools exfatprogs udftools ntfs-3g e2fsprogs
```

**Fedora:**
```bash
sudo dnf install dosfstools exfatprogs udftools ntfs-3g e2fsprogs
```

## Running from Source

Install briefcase in a venv:
```bash
python3 -m venv venv
source venv/bin/activate
pip install briefcase
```

Clone the project, and run in the root directory:
```bash
briefcase dev -r
```

Briefcase will check for missing system dependencies and tell you what to install if anything is missing.
