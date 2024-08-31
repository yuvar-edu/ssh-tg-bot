# SSH Telegram Bot

This project is a Telegram bot designed to interact with the Clore.ai, Vast.ai API, allowing authorized users (admins) to manage orders and execute commands on instances via SSH.

## Features

- View active orders from Clore.ai.
- Execute commands on individual instances or all instances in bulk.
- Supports SSH authentication using both password and public key methods.

## Requirements

- Python 3.7 or higher
- Telegram Bot API token
- Clore.ai API token
- SSH private key (if using public key authentication)

## Setup Instructions

### 1. Clone the repository

` git clone https://github.com/yuvar-edu/ssh-tg-bot.git `
` cd ssh-tg-bot `

### 2. Install dependencies
 - Install the necessary Python packages using pip:

 ` pip install -r requirements.txt `

 ### 4. Configuration

 - Change Telegram bot token, clore api token, admin chat id, path to key in main python file.

 ### 6. Running the Bot
 - To start the bot, simply run:

` python clore.py `
` python vast.py `

## Support:

 - a lil pocket money will be appreciated:
 - BTC: bc1qxddz9h5kvvl25vsqx3yvng0vcqfa7k06nyxljj