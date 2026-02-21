from nc_py_api import Nextcloud
from dotenv import load_dotenv
from openrouter import OpenRouter
from markitdown import MarkItDown
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from premailer import transform

import json
import os
import time
import markdown
import smtplib

load_dotenv()

AI_MODEL = "openai/gpt-oss-120b"

nc = Nextcloud(nextcloud_url = os.getenv("NEXTCLOUD_URL"), nc_auth_user = os.getenv("NEXTCLOUD_USER"), nc_auth_pass = os.getenv("NEXTCLOUD_PASS"))
md = MarkItDown()
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
emails = []

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
    if not os.path.exists("./map.json"):
        new_map = build_map(os.getenv("NEXTCLOUD_DIR"))
        with open("map.json", "w", encoding="utf8") as fs:
            fs.write(json.dumps(new_map, indent=4))

    while True:
        try:
            with open("./mailinglist.json", "r", encoding="utf-8") as fs:
                emails = json.load(fs)
        except:
            print("No mailing list specified. Please create 'mailinglist.json' and fill it with an array of target mails!")
            wait()
            continue

        new_map = build_map(os.getenv("NEXTCLOUD_DIR"))
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

        new_file_names = diff["files"]

        with OpenRouter(
            api_key=os.getenv("OPENROUTER_API_KEY")
        ) as client:
            response = client.chat.send(
                model = AI_MODEL,
                messages = [
                    {"role": "user", "content": """
                    Die folgenden Dateinamen könnten Teile von Hausaufgaben enthalten, es könnten aber auch unbrauchbare darunter sein.
                    Filtere Dateinamen heraus, die sicher nicht Teile von Hausaufgaben sind.
                    Abgaben und Lösungen gehören definitiv nicht zu Hausaufgaben und sollen aus der Liste herausgefiltert werden.
                    Hier sind die Dateinamen:
                    
                    """ + "\n".join(new_file_names)}
                ],
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "file_names",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "files": {
                                    "type": "array",
                                    "description": "File names which are part of Homework"
                                }
                            },
                            "required": ["files"],
                            "additionalProperties": False
                        }
                    }
                }
            )
            print(response.choices[0].message.content)
            new_file_names = json.loads(response.choices[0].message.content)["files"]

        os.makedirs("./download", exist_ok=True)

        for new_file in new_file_names:
            filename = new_file.split("/")[-1]

            with open(f"download/{filename}", "wb") as fs:
                fs.write(nc.files.download(new_file))

        uploading_files = []

        if os.path.exists("./download"):
            for file in os.listdir("./download"):
                try:
                    md_file = md.convert(f"./download/{file}")
                    uploading_files.append(f"{md_file.title}:\n")
                    uploading_files.append(md_file.text_content)
                except Exception as e:
                    print(f"ERROR CONVERTING {file} to MD: {e}")

        result = ""

        with OpenRouter(
            api_key=os.getenv("OPENROUTER_API_KEY")
        ) as client:
            result = client.chat.send(
                model=AI_MODEL,
                messages=[
                    {"role": "user", "content": """
                    Die folgenden Informationen enthalten eventuell Hausaufgaben.
                    Falls du hier Aufgaben erkennst, arbeite den Arbeitsauftrag heraus und verarbeite ihn zu einer vollständigen Lösung.
                    Gib mir die pure Lösung zu einzelnen Aufgaben, ohne Rückfragen.
                    Schreibe die Namen der Dateien an den Anfang deiner Antwort.
                    Ich kenne den Kontext der Hausaufgaben nicht, erkläre mir also kurz und knapp die Kernthemen.
                    Wenn du dir sicher bist, dass kein Arbeitsauftrag vorhanden ist, schreibe einfach nur 'kamma nix machen'.
                    
                    """ + "\n\n".join(uploading_files)}
                ],
            )

        print(result.choices[0].message.content)
        with open("./result.txt", "w", encoding="utf-8") as fh:
            fh.write(result.choices[0].message.content)

        rendered = markdown.markdown(result.choices[0].message.content, extensions=['markdown.extensions.tables'])
        rendered = transform(rendered)

        with open("./output.html", "w", encoding="utf-8") as fh:
            fh.write(rendered)

        for mail in emails:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = "Neue Hausaufgaben!!!"
                msg["From"] = EMAIL_ADDRESS

                text_body = "Bitte öffnen sie diese Mail in einem HTML fähigen client."

                part1 = MIMEText(text_body, "plain")
                part2 = MIMEText(rendered, "html")

                msg.attach(part1)
                msg.attach(part2)

                with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                    smtp.starttls()
                    smtp.login(EMAIL_ADDRESS, os.getenv("GOOGLE_APP_PASSWORD"))
                    msg["To"] = mail
                    smtp.send_message(msg)
                
                print(f"Email to '{mail}' was sent")
            except Exception as e:
                print(e)

        cleanup()

        wait()