# Linux Rufus (`linux-rufus`)

[![CI](https://github.com/amitpadhan979/linux-rufus/actions/workflows/ci.yml/badge.svg)](https://github.com/amitpadhan979/linux-rufus/actions)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

A reliable, safety-first Linux utility inspired by Pete Batard's iconic **Rufus** for creating bootable USB flash drives.

Unlike Windows Rufus (which is Windows-only), **`linux-rufus`** brings the beloved Rufus feature set and layout to Linux desktop and server users:
- **Classic Rufus UI**: Familiar desktop interface with device selection, boot scheme (MBR/GPT), target system (BIOS/UEFI), filesystem format, and progress indicators.
- **Interactive TUI & CLI**: Rich terminal user interface and scriptable command-line interface for headless servers or terminal power users.
- **Strict Safety Shield**: Auto-detects removable USB media and hard-blocks writes to system root (`/`), boot (`/boot`), home (`/home`), or swap drives to prevent accidental data loss.
- **Dual Burn Engines**:
  - **DD / Raw Stream Mode**: High-performance streaming write for Linux hybrid ISOs (`Ubuntu`, `Debian`, `Arch`, `Fedora`, etc.) and raw disk images (`.iso`, `.img`, `.raw`).
  - **Partition & Extract Mode**: Partitions (`GPT` / `MBR`), formats (`FAT32`, `NTFS`, `exFAT`, `ext4`), extracts contents, and configures UEFI boot structures.
- **Windows Media Support**: Automatically handles `install.wim` files exceeding FAT32's 4GB limit via WIM splitting or dual UEFI-NTFS setups.

---

## 🚀 Installation

### From Debian / Ubuntu (`.deb`) Package
Download the latest `linux-rufus_1.1.1_all.deb` from [Releases](https://github.com/amitpadhan979/linux-rufus/releases) and install via `apt`:
```bash
sudo apt install ./linux-rufus_1.1.1_all.deb
```

### Using pip
```bash
git clone https://github.com/amitpadhan979/linux-rufus.git
cd linux-rufus
pip install .
```

### For development / building `.deb`
```bash
git clone https://github.com/amitpadhan979/linux-rufus.git
cd linux-rufus
make dev
make deb   # Generates dist/linux-rufus_<version>_all.deb
```

---

## 🛠 Usage

### 1. Classic Rufus Desktop GUI
To launch the familiar Rufus graphical interface:
```bash
linux-rufus gui
```

### 2. Interactive Terminal UI (TUI)
Run without arguments or pass `tui` to open the interactive text menu:
```bash
linux-rufus tui
```

### 3. List Removable USB Devices Safely
Inspect all detected removable block devices:
```bash
linux-rufus list
```
*(Add `--all` to view internal drives and check their safety lock status).*

### 4. Inspect an ISO / Disk Image
Analyze bootloader signatures, volume labels, and recommended burn modes (add `--hash` to compute SHA256 and MD5):
```bash
linux-rufus info ubuntu-24.04-desktop-amd64.iso --hash
```

### 5. Burn Image via Command Line
```bash
# Burn using recommended mode (requires root / sudo for block writing)
sudo linux-rufus burn --iso ubuntu-24.04-desktop-amd64.iso --target /dev/sdb

# Burn with post-write data verification
sudo linux-rufus burn --iso ubuntu-24.04-desktop-amd64.iso --target /dev/sdb --verify

# Burn live Linux with 2GB persistent storage partition (casper-rw)
sudo linux-rufus burn --iso ubuntu-24.04-desktop-amd64.iso --target /dev/sdb --persistence-size 2G

# Burn with explicit partition scheme and filesystem
sudo linux-rufus burn --iso Win11.iso --target /dev/sdb --scheme GPT --fs fat32

# Burn Windows 11 with TPM and Secure Boot check bypasses
sudo linux-rufus burn --iso Win11.iso --target /dev/sdb --bypass-tpm --bypass-secure-boot
```

### 6. Quickstart Dry-Run Verification
To verify target integrity and parameter validity without writing to hardware or requiring root:
```bash
# Verify detected block devices
linux-rufus list --dry-run

# Simulate a burn operation safely with verification and persistence
linux-rufus burn --iso ubuntu-24.04-desktop-amd64.iso --target /dev/sdb --verify --persistence-size 2G --dry-run
```


---

## 🛡️ Safety Shield Architecture

Directly writing to block devices is a dangerous operation on Linux. `linux-rufus` implements a multi-layer safety lock:
1. **Removable Media Only**: By default, only devices flagged with `RM=1` or `TRAN=usb` are eligible targets.
2. **System Disk Blacklist**: Automatically inspects active mountpoints via `/proc/mounts` and `/proc/swaps`. Any device holding `/`, `/boot`, `/boot/efi`, `/home`, `/var`, `/usr`, or active swap partitions is hard-blocked.
3. **Resilient Hardware Discovery (v1.1.1+)**:
   - Tries modern JSON-capable `lsblk` (`MOUNTPOINTS` column) first, seamlessly falling back to legacy single-mountpoint columns on older `util-linux` distributions.
   - Gracefully handles restricted/containerized environments where `/sys/block` throws `PermissionError` (Errno 13) by falling back to `/proc/partitions` and `udevadm`/`blockdev`.
4. **Double Confirmation**: Both CLI and GUI display the target drive model, capacity, and require explicit confirmation before wiping partition tables.

---

## 🧪 Testing

Run the test suite:
```bash
make test
```

Or using `pytest`:
```bash
pytest -v
```

---

## 📜 License

Licensed under the **GNU General Public License v3.0** (`GPL-3.0-or-later`). See [LICENSE](LICENSE) for details.
