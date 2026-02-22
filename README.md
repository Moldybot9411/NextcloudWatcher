# Automatic Nextcloud Homework Solver

This script scans a specific NextCloud folder and checks if new homework was uploaded.<br>
New homework will automatically be solved by AI and sent to you via Email.

## How to use
- Pull this repo with `git pull https://github.com/Moldybot9411/NextcloudWatcher.git`
- Navigate to the folder it was downloaded to
- Copy `.env.example` and rename it to `.env`
    - You can create a Google App Key [here](https://myaccount.google.com/apppasswords). The app will be used to send mails from.
    - This script uses OpenRouter as the AI provider. You can use OpenRouter for free (but you must change the model to a free one in main.py [Variable name: AI_MODEL])
- Run `docker-compose up -d`
- A new `data` directory will be created as a mount folder.
- Copy `mailinglist.example.json` into this data folder and rename it to `mailinglist.json` and enter mails where solved homework should be sent to.
