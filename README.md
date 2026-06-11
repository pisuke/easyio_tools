# easyio_tools
Tools for when things with EasyIO devices get sticky

# easyio_update_udmi_metadata_refs

```
$ python3 easyio_update_udmi_metadata_refs.py --help
usage: easyio_update_udmi_metadata_refs.py [-h] [-p PROJECTS_DIR] [-d DATED_FOLDER]
                                           [-u UDMI_DIR] [-b] [--dry-run] [-v]

Update UDMI device metadata.json point 'ref' fields from EasyIO backup archives.

options:
  -h, --help            show this help message and exit
  -p, --projects-dir PROJECTS_DIR
                        Base directory containing dated project folders (default:
                        /home/fanselmo/Code/easyio_tools/batch_tools/data/projects)
  -d, --dated-folder DATED_FOLDER
                        Specific dated folder name or path to process (if not specified, auto-
                        picks the latest one)
  -u, --udmi-dir UDMI_DIR
                        Path to UDMI devices folder hierarchy (default:
                        /home/fanselmo/Code/easyio_tools/sites/UK-LON-KGX1/udmi/devices)
  -b, --backup          Create a timestamped backup (e.g.
                        metadata.json.YYYYMMDD_HHMMSS.bak.json) before modifying original files
  --dry-run             Perform a dry run without modifying or backing up any files
  -v, --verbose         Print detailed progress and inspection logs

```
