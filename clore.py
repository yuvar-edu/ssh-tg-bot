import logging
import requests
import paramiko
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CLORE_API_TOKEN = 'ur_clore_token'
TELEGRAM_BOT_TOKEN = 'ur_bot_token'
SSH_KEY_PATH = ''
ADMIN_CHAT_IDS = []  # Replace with your admin chat ID(s)

# Conversation states
CHOOSE_ORDER, CHOOSE_AUTH_METHOD, ENTER_PASSWORD, ENTER_COMMAND, BULK_COMMAND = range(5)

# Function to check if user is admin
def is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_CHAT_IDS

# Admin-only decorator
def admin_only(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if not is_admin(update):
            update.message.reply_text("Sorry, this bot is only accessible to admins.")
            return ConversationHandler.END
        return func(update, context, *args, **kwargs)
    return wrapper

# Function to fetch orders from Clore.ai
def get_orders():
    url = 'https://api.clore.ai/v1/my_orders'
    headers = {'auth': CLORE_API_TOKEN}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get('orders', []) if data.get('code') == 0 else []
    except requests.RequestException as e:
        logger.error(f"Error fetching orders: {e}")
        return []

# Start command handler
@admin_only
def start(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton("View My Orders", callback_data="view_orders")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Welcome to the Clore.ai Bot! Choose an option:', reply_markup=reply_markup)
    return CHOOSE_ORDER

# Display orders to the user
def show_orders(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    orders_list = get_orders()

    if not orders_list:
        query.edit_message_text("No active orders found.")
        return ConversationHandler.END

    keyboard = []
    for order in orders_list:
        button_text = f"Order ID: {order['id']} | GPU: {order['specs']['gpu']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"order_{order['id']}")])

    # Adding "Back" and "Close" buttons
    keyboard.append([InlineKeyboardButton("Close", callback_data="close")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text='Select an order:', reply_markup=reply_markup)
    return CHOOSE_ORDER

# Handle order selection
def handle_order_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    selected_order_id = query.data

    if selected_order_id == "bulk_command":
        query.edit_message_text('Please enter the command to run on all instances:')
        return BULK_COMMAND

    if selected_order_id.startswith("order_"):
        order_id = selected_order_id.split("_")[1]
        orders_list = get_orders()
        selected_order = next((order for order in orders_list if str(order['id']) == order_id), None)

        if selected_order:
            host, port = get_host_and_port(selected_order)
            context.user_data['host'] = host
            context.user_data['port'] = port
            context.user_data['current_order_id'] = order_id

            # Check if the auth method was previously set
            if 'auth_method' in context.user_data:
                query.edit_message_text('Please enter the command you want to run:')
                return ENTER_COMMAND

            keyboard = [
                [InlineKeyboardButton("Password", callback_data="password")],
                [InlineKeyboardButton("Public Key", callback_data="public_key")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text='Choose your authentication method:', reply_markup=reply_markup)
            return CHOOSE_AUTH_METHOD
        else:
            query.edit_message_text("Order not found. Please try again.")
            return CHOOSE_ORDER

    elif selected_order_id == "start":
        start(update, context)
        return CHOOSE_ORDER

    elif selected_order_id == "close":
        query.edit_message_text("Goodbye!")
        return ConversationHandler.END

    query.edit_message_text("Invalid selection. Please try again.")
    return CHOOSE_ORDER

# Extract host and port from an order
def get_host_and_port(order):
    host = order['pub_cluster'][0]  # Use the first public cluster host
    ssh_port = next((int(port.split(':')[1]) for port in order.get('tcp_ports', []) if port.startswith('22:')), 22)
    return host, ssh_port

# Authentication method handler
def choose_auth_method(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    auth_method = query.data
    context.user_data['auth_method'] = auth_method

    if auth_method == 'password':
        query.edit_message_text('Please enter your password:')
        return ENTER_PASSWORD
    elif auth_method == 'public_key':
        query.edit_message_text('Please enter the command you want to run:')
        return ENTER_COMMAND
    else:
        query.edit_message_text('Invalid choice. Please try again.')
        return CHOOSE_AUTH_METHOD

# Password entry handler
def enter_password(update: Update, context: CallbackContext) -> int:
    context.user_data['password'] = update.message.text
    update.message.reply_text('Please enter the command you want to run:')
    return ENTER_COMMAND

# Command entry handler for single instance
def enter_command(update: Update, context: CallbackContext) -> int:
    command = update.message.text
    host = context.user_data['host']
    port = context.user_data['port']
    auth_method = context.user_data.get('auth_method')

    if auth_method == 'password' and 'password' in context.user_data:
        password = context.user_data.get('password')
        output = ssh_with_password(host, port, 'root', password, command)
    elif auth_method == 'public_key':
        output = ssh_with_key(host, port, 'root', command)
    else:
        update.message.reply_text("Authentication method not found. Please start again.")
        return ConversationHandler.END

    update.message.reply_text(f"Output from instance {host}:\n{output}")

    keyboard = [
        [InlineKeyboardButton("Run Another Command", callback_data=f"order_{context.user_data['current_order_id']}")],
        [InlineKeyboardButton("Back to Orders", callback_data="view_orders")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("What would you like to do next?", reply_markup=reply_markup)

    return CHOOSE_ORDER

# Command entry handler for all instances
def bulk_command(update: Update, context: CallbackContext) -> int:
    command = update.message.text
    orders_list = get_orders()
    results = {}
    for order in orders_list:
        host, port = get_host_and_port(order)
        output = ssh_with_key(host, port, 'root', command)
        results[order['id']] = output

    result_text = "\n\n".join([f"Order {order_id}:\n{output}" for order_id, output in results.items()])
    update.message.reply_text(f"Outputs from all instances:\n{result_text}")

    keyboard = [
        [InlineKeyboardButton("Back to Orders", callback_data="view_orders")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("What would you like to do next?", reply_markup=reply_markup)

    return CHOOSE_ORDER

# SSH into a server using public key
def ssh_with_key(host, port, username, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=username, key_filename=SSH_KEY_PATH, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8').strip()
        error = stderr.read().decode('utf-8').strip()
        ssh.close()

        if output:
            return output
        elif error:
            return f"Error: {error}"
        else:
            return "Command executed, but there was no output."

    except paramiko.AuthenticationException:
        return "Authentication failed, please verify your credentials."
    except paramiko.SSHException as e:
        return f"Unable to establish SSH connection: {str(e)}"
    except Exception as e:
        return f"An error occurred while connecting: {str(e)}"

# SSH into a server using password
def ssh_with_password(host, port, username, password, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=username, password=password, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8').strip()
        error = stderr.read().decode('utf-8').strip()
        ssh.close()

        if output:
            return output
        elif error:
            return f"Error: {error}"
        else:
            return "Command executed, but there was no output."

    except paramiko.AuthenticationException:
        return "Authentication failed, please verify your credentials."
    except paramiko.SSHException as e:
        return f"Unable to establish SSH connection: {str(e)}"
    except Exception as e:
        return f"An error occurred while connecting: {str(e)}"

# Error handler
def error(update: Update, context: CallbackContext):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# Main function to start the bot
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ORDER: [
                CallbackQueryHandler(show_orders, pattern='^view_orders$'),
                CallbackQueryHandler(handle_order_selection)
            ],
            CHOOSE_AUTH_METHOD: [CallbackQueryHandler(choose_auth_method)],
            ENTER_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, enter_password)],
            ENTER_COMMAND: [MessageHandler(Filters.text & ~Filters.command, enter_command)],
            BULK_COMMAND: [MessageHandler(Filters.text & ~Filters.command, bulk_command)],
        },
        fallbacks=[CommandHandler('cancel', start)],
    )

    dp.add_handler(conv_handler)
    dp.add_error_handler(error)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
