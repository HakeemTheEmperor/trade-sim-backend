from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
import os
import requests
from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.exchangerate import ExchangeRate
from ..models.transactions import Transaction, TransactionType, TransactionCategory
from .. import db

EXCHANGE_RATE_API = os.getenv("EXCHANGE_RATE_API")

class WalletService:
    def get_exchange_rate(self, from_currency, to_currency):
        rate_record = ExchangeRate.query.filter_by(base_currency=from_currency, target_currency=to_currency).first()
        if rate_record and rate_record.last_updated > datetime.now(timezone.utc) - timedelta(hours=24):
            return rate_record.rate
        
        new_rate = self.fetch_from_api(from_currency, to_currency)
        if rate_record:
            rate_record.rate = new_rate
            rate_record.last_updated = datetime.now(timezone.utc)
        else:
            rate_record = ExchangeRate(
                base_currency = from_currency,
                target_currency = to_currency,
                rate = new_rate,
                last_updated = datetime.now(timezone.utc)
            )
            db.session.add(rate_record)
        
        db.session.commit()
        return new_rate
        
    def fetch_from_api(self, from_currency, to_currency):
        try:
            url = f"{EXCHANGE_RATE_API}/{from_currency.value}/{to_currency.value}"
            print(url)
            response = requests.get(url)
            data = response.json()

            if data.get("result") != "success":
                raise ValueError("Failed to fetch exchange rate")
            return data.get("conversion_rate")
        except Exception as e:
            raise ValueError(f"Error fetching exchange rate: {str(e)}")
        
        
    def get_user_wallets(self, user_id):
        try:            
            wallets = Wallet.query.filter_by(user_id=user_id).all()
            if wallets:
                return [wallet.to_dict() for wallet in wallets]
            return []
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def get_wallet_by_id(self, user_id, wallet_id):
        try:
            wallet = Wallet.query.filter_by(id=wallet_id, user_id = user_id).first()
            if not wallet:
                return []
            return wallet.to_dict()
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def create_wallet(self, user_id, currency_enum):
        try:
            new_wallet = Wallet(user_id=user_id, currency=currency_enum, balance=0)
            db.session.add(new_wallet)
            db.session.commit()
            return new_wallet.to_dict()
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
    
    def get_wallet_by_currency(self, user_id, currency):
        return Wallet.query.filter_by(user_id=user_id, currency=currency).first()
    
    def delete_wallet(self, user_id, wallet_id):
        wallet = Wallet.query.filter_by(id=wallet_id, user_id=user_id).first()
        if not wallet:
            raise ValueError("Wallet not found. Are you sure it exists?")
        if wallet.balance > 0:
            raise ValueError("Cannot delete a wallet with balance in it. Try closing the wallet instead") 
        db.session.delete(wallet)
        db.session.commit()
        return {"message": "Wallet deleted successfully"}
    
    def transfer_funds(self, from_wallet_id, to_wallet_id, amount, user_id):
        print(f"from_wallet_id: {from_wallet_id}, type: {type(from_wallet_id)}")
        print(f"to_wallet_id: {to_wallet_id}, type: {type(to_wallet_id)}")

        from_wallet = Wallet.query.filter_by(id=from_wallet_id).first()
        to_wallet = Wallet.query.filter_by(id=to_wallet_id).first()
        
        if not from_wallet or not to_wallet:
            raise ValueError("Invalid wallet Id entered")
        if int(from_wallet.user_id) != int(user_id):
            raise ValueError("We could not find the wallet you entered")
        # If the sender's wallet balance is less than the amount to be transferred, return error
        if from_wallet.balance < amount:
            raise ValueError("Insufficient funds in the source wallet")
        converted_amount = amount
        
        # If currencies are different, get exchange rate and convert from senders currency to receivers currency
        if from_wallet.currency != to_wallet.currency:
            rate = self.get_exchange_rate(from_wallet.currency, to_wallet.currency)
            if not rate:
                raise ValueError("Exchange rate not available")
            converted_amount = amount * rate
        
        try:
            from_wallet.balance -= amount
            to_wallet.balance += converted_amount
            
            
            # Log transactions
            sender_transaction = Transaction(
                user_id=from_wallet.user_id,
                from_wallet_id=from_wallet.id,
                to_wallet_id=to_wallet_id,
                transaction_type=TransactionType.DEBIT,
                transaction_category=TransactionCategory.WALLET_TRANSFER,
                total_value=-amount,
                currency=from_wallet.currency,
            )
            receiver_transaction = Transaction(
                user_id=to_wallet.user_id,
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet.id,
                transaction_type=TransactionType.CREDIT,
                transaction_category=TransactionCategory.WALLET_TRANSFER,
                total_value=converted_amount,
                currency=to_wallet.currency,
            )
            db.session.add(sender_transaction)
            db.session.add(receiver_transaction)
            db.session.commit()
            return {"message": "Funds transferred successfully"}
        except IntegrityError:
            db.session.rollback()
            raise RuntimeError("Transaction failed, please try again later")
        