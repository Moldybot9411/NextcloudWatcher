# Automatic Nextcloud Homework Solver

This script scans a specific NextCloud folder and checks if new homework was uploaded.<br>
New homework will automatically be solved by AI and sent to you via Email.

## How to use
- Copy `.env.example` and rename it to `.env`
    - You can create a Google App Key [here](https://myaccount.google.com/apppasswords). The app will be used to send mails from.
- Run `docker-compose up -d`
- A new `data` directory will be created as a mount folder.
- Copy `mailinglist.example.json` into this data folder and rename it to `mailinglist.json` and enter mails where solved homework should be sent to.