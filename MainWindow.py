# -*- coding: utf-8 -*-
""" MainWindow.py

This file represents the main wallet window, and the underlying
logic required for it. It loads the corresponding Glade file, of
the same name.
"""

from datetime import datetime
import threading
import time
from gi.repository import Gtk, Gdk, GLib
import tzlocal
from __init__ import __version__
import global_variables


class MainWindow(object):
    """
    This class is used to interact with the MainWindow glade file
    """
    def on_MainWindow_destroy(self, object, data=None):
        """Called by GTK when the main window is destroyed"""
        Gtk.main_quit() # Quit the GTK main loop

    def on_CopyButton_clicked(self, object, data=None):
        """Called by GTK when the copy button is clicked"""
        self.builder.get_object("AddressTextBox")
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.builder.get_object("AddressTextBox").get_text(), -1)

    def on_AboutMenuItem_activate(self, object, data=None):
        """Called by GTK when the 'About' menu item is clicked"""
        # Get the about dialog from the builder
        about_dialog = self.builder.get_object("AboutDialog")

        # Set the version on the about dialog to correspond to that of the init file
        about_dialog.set_version("v{0}".format(__version__))

        # Run the dialog and await for it's response (in this case to be closed)
        about_dialog.run()

        # Hide the dialog upon it's closure
        about_dialog.hide()

    def update_loop(self):
        """
        This method loops infinitely and refreshes the UI every 5 seconds.

        Note:
            More optimal differential method of reloading transactions
            is required, as currently you can't really scroll through them
            without it jumping back to the top when it clears the list.
            Likely solution would be a hidden (or not) column with the
            transaction hash."""
        while True:
            GLib.idle_add(self.refresh_values) # Refresh the values, calling the method via GLib
            time.sleep(5) # Wait 5 seconds before doing it again

    def refresh_values(self):
        """
        This method refreshes all the values in the UI to represent the current
        state of the wallet.
        """

        # Request the balance from the wallet
        balances = global_variables.wallet_connection.request("getBalance")
        # Update the balance amounts, formatted as comma seperated with 2 decimal points
        self.builder.get_object("AvailableBalanceAmountLabel").set_label("{:,.2f}".format(balances['availableBalance']/100.))
        self.builder.get_object("LockedBalanceAmountLabel").set_label("{:,.2f}".format(balances['lockedAmount']/100.))

        # Request the addresses from the wallet (looks like you can have multiple?)
        addresses = global_variables.wallet_connection.request("getAddresses")['addresses']
        # Load the first address in for now - TODO: Check if multiple addresses need accounting for
        self.builder.get_object("AddressTextBox").set_text(addresses[0])

        # Request the current status from the wallet
        status = global_variables.wallet_connection.request("getStatus")

        # Request all transactions related to our addresses from the wallet
        # This returns a list of blocks with only our transactions populated in them
        blocks = global_variables.wallet_connection.request("getTransactions", params={"blockCount" : status['blockCount'], "firstBlockIndex" : 1, "addresses": addresses})['items']

        # Clear the transaction list store ready to (re)populate
        self.transactions_list_store.clear()

        # Iterate through the blocks and extract the relevant data
        # This is reversed to show most recent transactions first
        for block in reversed(blocks):
            if block['transactions']: # Check the block contains any transactions
                for transaction in block['transactions']: # Loop through each transaction in the block
                    # To locate the address, we need to find the relevant transfer within the transaction
                    address = None
                    if transaction['amount'] < 0: # If the transaction was sent from this address
                        # Get the desired transfer amount, accounting for the fee and the transaction being
                        # negative as it was sent, not received
                        desired_transfer_amount = (transaction['amount'] + transaction['fee']) * -1
                    else:
                        desired_transfer_amount = transaction['amount']
                    
                    # Now loop through the transfers and find the address with the correctly transferred amount
                    for transfer in transaction['transfers']:
                        if transfer['amount'] == desired_transfer_amount:
                            address = transfer['address']

                    # Append the transaction to the treeview's backing list store in the correct format
                    self.transactions_list_store.append([
                        # Determine the direction of the transfer (In/Out)
                        "In" if transaction['amount'] > 0 else "Out",
                        # Determine if the transaction is confirmed or not - block rewards take 40 blocks to confirm,
                        # transactions between wallets are marked as confirmed automatically with unlock time 0
                        transaction['unlockTime'] is 0 or transaction['unlockTime'] <= status['blockCount'] - 40,
                        # Format the amount as comma seperated with 2 decimal points
                        "{:,.2f}".format(transaction['amount']/100.),
                        # Format the transaction time for the user's local timezone
                        datetime.fromtimestamp(transaction['timestamp'], tzlocal.get_localzone()).strftime("%Y/%m/%d %H:%M:%S%z (%Z)"),
                        # The address as located earlier
                        address
                    ])
        # Update the status label in the bottom right with block height, peer count, and last refresh time
        self.builder.get_object("MainStatusLabel").set_label("Current block height: {0} | Peer count {1} | Last Updated {2}".format(status['blockCount'], status['peerCount'], datetime.now(tzlocal.get_localzone()).strftime("%H:%M:%S")))

    def __init__(self):
        # Initialise the GTK builder and load the glade layout from the file
        self.builder = Gtk.Builder()
        self.builder.add_from_file("MainWindow.glade")

        # Get the transaction treeview's backing list store
        self.transactions_list_store = self.builder.get_object("HomeTransactionsListStore")

        # Use the methods defined in this class as signal handlers
        self.builder.connect_signals(self)

        # Get the window from the builder
        self.window = self.builder.get_object("MainWindow")

        # Set the window title to reflect the current version
        self.window.set_title("TurtleWallet v{0}".format(__version__))

        # Start the UI update loop in a new thread
        self.update_thread = threading.Thread(target=self.update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()

        # Finally, show the window
        self.window.show_all()
