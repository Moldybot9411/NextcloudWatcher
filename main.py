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
import logging
import shutil

# Set data directory for persistent storage
DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
DOWNLOAD_DIR = os.path.join(DATA_DIR, "download")

# Configure logging
log_file = os.path.join(DATA_DIR, "app.log")
logger = logging.getLogger(__name__)
logging.basicConfig(
    filename=log_file,
    encoding='utf-8',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

AI_MODEL = "openai/gpt-oss-120b"
MAX_TRIES = 3
TIME_BETWEEN_TRIES = 300 # 5 Minutes

NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER")
NEXTCLOUD_PASS = os.getenv("NEXTCLOUD_PASS")
NEXTCLOUD_DIR = os.getenv("NEXTCLOUD_DIR")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
ADMIN_MAIL = os.getenv("ADMIN_MAIL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_APP_PASSWORD = os.getenv("GOOGLE_APP_PASSWORD")

logger.info("=== Trying NextCloud Login ===")
try:
    nc = Nextcloud(nextcloud_url = NEXTCLOUD_URL, nc_auth_user = NEXTCLOUD_USER, nc_auth_pass = NEXTCLOUD_PASS)
    logger.info("Login was successful!")
except:
    logger.error("NextCloud Login failed. Aborting...")
    quit()

md = MarkItDown()

def initialize_mails() -> list[str]:
    result: list[str] = []
    logger.info("=== Loading Mails from mailinglist.json ===")

    mailing_list_path = os.path.join(os.getenv("DATA_DIR", "./data"), "mailinglist.json")
    try:
        with open(mailing_list_path, "r", encoding="utf8") as fs:
            list = json.load(fs)
            result = list
    except:
        logger.warning("Failed to load mailing list. No Mails will be sent!")
    
    return result


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
    logger.info("Building file map")
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
    logger.info("Cleaning up temporary folders")
    try:
        download_path = os.path.join(DATA_DIR, "download")
        if (os.path.exists(download_path)):
            shutil.rmtree(download_path)
    except Exception as e:
        logger.error("Error deleting download folder: %s", e)

def wait():
    logger.info("Next check in 10 hrs")
    time.sleep(36000)

def filter_file_names(names: list[str]) -> list[str]:
    result: list[str] = []
    current_try = 0

    while (current_try < MAX_TRIES):
        logger.info("Filtering file names [%d/%d]", current_try + 1, MAX_TRIES)

        try:
            with OpenRouter(
                api_key = OPENROUTER_API_KEY
            ) as client:
                response = client.chat.send(
                    model = AI_MODEL,
                    messages = [
                        {"role": "user", "content": """
                        Die folgenden Dateinamen könnten Teile von Hausaufgaben enthalten, es könnten aber auch unbrauchbare darunter sein.
                        Filtere Dateinamen heraus, die sicher nicht Teile von Hausaufgaben sind.
                        Abgaben und Lösungen gehören definitiv nicht zu Hausaufgaben und sollen aus der Liste herausgefiltert werden.
                        Hier sind die Dateinamen:
                        
                        """ + "\n".join(names)}
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

            result = json.loads(response.choices[0].message.content)["files"]
            break
        except Exception as e:
            logger.error("Error filtering file names. Retrying in 5 Minutes: %s", e)
            current_try += 1
            time.sleep(TIME_BETWEEN_TRIES)

    return result

def convert_downloads_to_md() -> list[str]:
    result: list[str] = []

    try:
        download_path = os.path.join(DATA_DIR, "download")
        if os.path.exists(download_path):
            for file in os.listdir(download_path):
                element = ""
                try:
                    md_file = md.convert(f"{download_path}/{file}")

                    element = f"```text\nFilename: {md_file.title}:\n"
                    element += md_file.text_content
                except Exception as e:
                    logger.error("ERROR CONVERTING %s to MD", file)

                    element = f"```\nFilename: {file}\nThis File could not be converted to Markdown. Please provide this information in your output."

                result.append(element)
    except Exception as e:
        logger.error("Failed to solve homework: %s", e)
    
    return result

def send_admin_info_mail(content: str):
    current_try = 0

    while (current_try < MAX_TRIES):
        try:
            logger.info("Sending Admin Mail [%d/%d]", current_try + 1, MAX_TRIES)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "NextCloud Scanner Info"
            msg["From"] = EMAIL_ADDRESS

            text_body = content

            part1 = MIMEText(text_body, "plain")

            msg.attach(part1)

            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_ADDRESS, os.getenv("GOOGLE_APP_PASSWORD"))
                msg["To"] = ADMIN_MAIL
                smtp.send_message(msg)
            
            logger.info("Admin Info Mail to '%s' was sent", ADMIN_MAIL)

            break
        except Exception as e:
            logger.error("Error sending Admin Mail to '%s': %s", ADMIN_MAIL, e)
            current_try += 1
            time.sleep(TIME_BETWEEN_TRIES)

def send_user_mail(mailing_list: list[str], rendered_html: str):
    current_try = 0

    while (current_try < MAX_TRIES):
        try:
            logger.info("Sending User Mail [%d/%d]", current_try + 1, MAX_TRIES)

            for mail in mailing_list:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = "New Homework!"
                msg["From"] = EMAIL_ADDRESS

                text_body = "Please open this Mail in an HTML-capable client."

                part1 = MIMEText(text_body, "plain")
                part2 = MIMEText(rendered_html, "html")

                msg.attach(part1)
                msg.attach(part2)

                with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                    smtp.starttls()
                    smtp.login(EMAIL_ADDRESS, GOOGLE_APP_PASSWORD)
                    msg["To"] = mail
                    smtp.send_message(msg)
                
                logger.info("Email to '%s' was sent", mail)

            break
        except Exception as e:
            logger.error("Error sending User Mail to '%s': %s", mail, e)
            current_try += 1
            time.sleep(TIME_BETWEEN_TRIES)

def solve_homework(file_contents: list[str]) -> str:
    result = ""
    current_try = 0

    while (current_try < MAX_TRIES):
        try:
            logger.info("Solving Homework [%d/%d]", current_try + 1, MAX_TRIES)

            with OpenRouter(
                api_key=os.getenv("OPENROUTER_API_KEY")
            ) as client:
                response = client.chat.send(
                    model=AI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content":"""
                            The following files could eventually contain Homework.
                            If you can detect Homework, familiarize yourself with the task/s and provide a full solution.
                            Your Output shall be the pure solution with no questions, as this output is used to be sent via E-Mail.
                            Write all the file names used in your solution on the top of your response.
                            The context of the Homework is unknown to the recipient, so explain in a few short sentences the core topics of the Homework.
                            If you are sure there is no Homework, please say so in your output but still summarize the content of the files.
                            Answer in the language of the provided files."""
                        },
                        {
                            "role": "user",
                            "content": "\n\n".join(file_contents)
                        }
                    ],
                )
            
            result = response.choices[0].message.content
            
            break
        except Exception as e:
            logger.error("Failed to solve Homework. Retrying in 5 Minutes: %s", e)
            current_try += 1
            time.sleep(TIME_BETWEEN_TRIES)

    return result

if __name__ == "__main__":
    map_file = os.path.join(DATA_DIR, "map.json")
    result_file = os.path.join(DATA_DIR, "result.md")
    output_file = os.path.join(DATA_DIR, "output.html")
    
    if not os.path.exists(map_file):
        logger.info("No file map has been detected. Building from %s", NEXTCLOUD_DIR)

        new_map = build_map(NEXTCLOUD_DIR)
        with open(map_file, "w", encoding="utf8") as fs:
            fs.write(json.dumps(new_map, indent=4))

    cleanup()
    while True:
        emails = initialize_mails()
        new_map = build_map(os.getenv("NEXTCLOUD_DIR"))
        old_map = {}
        diff = {}

        logger.info("Building map diff")
        with open(map_file, "r", encoding="utf-8")as fs:
            old_map = json.load(fs)
            diff = compare_map(old_map, new_map)

        if len(diff["files"]) == 0 and len(diff["directories"]) == 0:
            logger.info("No new files have been found.")
            cleanup()
            wait()
            continue
        
        # Inform Admin that new files were uploaded. If this mail is received but nothing comes after, something is wrong.
        send_admin_info_mail("New Files were uploaded to NextCloud! Check if you got the solution Mail.")
        
        with open(map_file, "w", encoding="utf8") as fs:
            fs.write(json.dumps(new_map, indent=4))

        # Gets all the new files from the diff and filters them based on file names
        new_file_names = diff["files"]
        new_file_names = filter_file_names(new_file_names)

        # Download files from NextCloud
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        for new_file in new_file_names:
            filename = new_file.split("/")[-1]

            with open(f"{DOWNLOAD_DIR}/{filename}", "wb") as fs:
                fs.write(nc.files.download(new_file))

        # Convert files to MarkDown and solve tasks
        file_contents = convert_downloads_to_md()
        logger.info("Uploading %d file/s to be solved", len(file_contents))

        result = solve_homework(file_contents)

        with open(result_file, "w", encoding="utf-8") as fh:
            fh.write(result)

        # Render MarkDown AI response to HTML to be displayed in Emails
        rendered = markdown.markdown(result, extensions=['markdown.extensions.tables'])
        rendered = transform(rendered)

        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(rendered)

        send_user_mail(emails, rendered)

        cleanup()
        wait()