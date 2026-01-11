from nc_py_api import Nextcloud
from dotenv import load_dotenv
import json
import os

load_dotenv()

def compare_map(old_map, new_map):
    new_items = {
        "directories": [],
        "files": []
    }

    def is_directory(node):
        return isinstance(node, dict) and any(isinstance(v, dict) for v in node.values())

    def is_file(node):
        return isinstance(node, dict) and "full_path" in node and not is_directory(node)

    def collect_all_recursive(node):
        """Erfasst rekursiv alle Inhalte eines neuen Verzeichnisses."""
        if not isinstance(node, dict):
            return

        for key, value in node.items():
            if key in ["full_path", "last_modified"]:
                continue
            
            if is_directory(value):
                new_items["directories"].append(value.get("full_path"))
                collect_all_recursive(value)
            elif is_file(value):
                new_items["files"].append(value.get("full_path"))

    def compare_recursive(old_node, new_node):
        for key, value in new_node.items():
            if key in ["full_path", "last_modified"]:
                continue
            
            if key not in old_node:
                if is_directory(value):
                    new_items["directories"].append(value.get("full_path"))
                    collect_all_recursive(value)
                elif is_file(value):
                    new_items["files"].append(value.get("full_path"))
            
            elif is_directory(value) and is_directory(old_node.get(key)):
                compare_recursive(old_node[key], value)

    compare_recursive(old_map, new_map)
    
    new_items["directories"] = sorted(list(set(filter(None, new_items["directories"]))))
    new_items["files"] = sorted(list(set(filter(None, new_items["files"]))))
    
    return new_items

def build_map(directory: str) -> object:

    def list_dir(directory: str, cur_folder: dict = {}):
        for node in nc.files.listdir(directory):
            if node.is_dir:
                cur_folder[node.name] = {
                    "full_path": node.user_path,
                    "is_dir": True
                }

                list_dir(node, cur_folder[node.name])
            else:
                cur_folder[node.name] = {
                    "last_modified": int(node.info.last_modified.timestamp()),
                    "full_path": node.user_path
                }

        return cur_folder
  
    return list_dir(directory);

if __name__ == "__main__":
    nc = Nextcloud(nextcloud_url = os.getenv("NEXTCLOUD_URL"), nc_auth_user = os.getenv("NEXTCLOUD_USER"), nc_auth_pass = os.getenv("NEXTCLOUD_PASS"))

    

    print("Files on the instance for the selected user:")
    full_map = build_map("e2fi4/BFK-B/")

    with open("map.json", "r", encoding="utf-8")as fs:
        old_map = json.load(fs)
        res = compare_map(old_map, full_map)
        print(res)

    quit()
    with open("map.json", "w", encoding="utf8") as fs:
        fs.write(json.dumps(full_map, indent=4))

    nc.files.download_directory_as_zip
    exit(0)