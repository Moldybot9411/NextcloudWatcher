from nc_py_api import Nextcloud
from dotenv import load_dotenv
from google import genai

import shutil
import json
import os
import time

load_dotenv()

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# for m in gemini_client.models.list():
#     for action in m.supported_actions:
#         if action == "generateContent":
#             print(m.name)

# quit()

def compare_map(old_map, new_map):
    new_items = {
        "directories": [],
        "files": []
    }

    def is_directory(node):
        return isinstance(node, dict) and node.get("is_dir", False)

    def is_file(node):
        return isinstance(node, dict) and not is_directory(node)

    def collect_all_recursive(node):
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
  
    return list_dir(directory)

def cleanup():
    try:
        os.remove("./Aufgabe.zip")
        os.remove("./download")
    except:
        return

def wait():
    print("Waiting for 10 hrs...")
    time.sleep(36000)

if __name__ == "__main__":
    nc = Nextcloud(nextcloud_url = os.getenv("NEXTCLOUD_URL"), nc_auth_user = os.getenv("NEXTCLOUD_USER"), nc_auth_pass = os.getenv("NEXTCLOUD_PASS"))

    if not os.path.exists("./map.json"):
        new_map = build_map("e2fi4/BFK-B/")
        with open("map.json", "w", encoding="utf8") as fs:
            fs.write(json.dumps(new_map, indent=4))

    while True:
        new_map = build_map("e2fi4/BFK-B/")
        old_map = {}
        diff = {}

        with open("map.json", "r", encoding="utf-8")as fs:
            old_map = json.load(fs)
            diff = compare_map(old_map, new_map)
            print(diff)

        if len(diff["files"]) == 0 and len(diff["directories"]) == 0:
            print("No new files uploaded!")
            cleanup()
            wait()
            continue
        
        with open("map.json", "w", encoding="utf8") as fs:
            fs.write(json.dumps(new_map, indent=4))

        os.makedirs("./download", exist_ok=True)

        for new_file in diff["files"]:
            filename = new_file.split("/")[-1]

            with open(f"download/{filename}", "wb") as fs:
                fs.write(nc.files.download(new_file))

        shutil.make_archive("Aufgabe", 'zip', "./download")

        uploading_file = gemini_client.files.upload(file="./Aufgabe.zip", config={"mime_type": "text/plain"})

        result = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                uploading_file,
                "\n\n",
                """
                Dieser Ordner enthält eventuell Hausaufgaben.
                Falls du hier Hausaufgaben erkennst, arbeite den Arbeitsauftrag heraus und verarbeite ihn zu einer vollständigen Lösung.
                Gib mir die pure Lösung zu einzelnen Aufgaben, ohne Rückfragen.
                Falls kein Arbeitsauftrag vorhanden zu sein scheint, schreibe einfach nur 'kamma nix machen'.
                """,
            ],
        )

        with open("./result.txt", "w", encoding="utf-8") as fh:
            fh.write(result.text)

        print(f"{result.text}")

        cleanup()

        wait()