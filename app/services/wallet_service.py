from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
import os
import requests
from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.exchangerate import ExchangeRate
from ..models.transactions import Transaction, TransactionType, TransactionCategory
from .. import db
from ..custom_exceptions import AlreadyExists, DataNotFound, InsufficientFunds, MissingProperties
from ..utils.enums_utils import ErrorStatuses
from ..utils.validation_utils import validate_positive_number, validate_wallet_id

EXCHANGE_RATE_API = os.getenv("EXCHANGE_RATE_API")

# Never let an outbound call hang a request/worker indefinitely.
REQUEST_TIMEOUT_SECONDS = 10

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
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            data = response.json()
            if data.get("result") != "success":
                raise DataNotFound("Failed to fetch exchange rate")
            # Return Decimal so it composes with the Numeric balance/amount math.
            return Decimal(str(data.get("conversion_rate")))
        except DataNotFound:
            raise
        except Exception as e:
            raise ValueError(f"Error fetching exchange rate: {str(e)}")
        
        
    def get_user_wallets(self, user_id):
        try:            
            wallets = Wallet.query.filter_by(user_id=user_id).all()
            if not wallets:
                raise DataNotFound("We could not find any wallet for this user", ErrorStatuses.WALLET_NOT_FOUND.value)
            return [wallet.to_dict() for wallet in wallets]
        except DataNotFound:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def get_wallet_by_id(self, user_id, wallet_id):
        try:
            wallet = Wallet.query.filter_by(id=wallet_id, user_id = user_id).first()
            if not wallet:
                raise DataNotFound("We could not find the wallet specified. Contact support if you think a mistake has been made", ErrorStatuses.WALLET_NOT_FOUND.value)
            return wallet.to_dict()
        except DataNotFound:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def create_wallet(self, user_id, currency):
        try:
            if not currency:
                raise MissingProperties("You did not enter a currency")
            currency_enum = WalletCurrencyType[currency]
            existing_wallet = self.get_wallet_by_currency(user_id, currency_enum)
            if existing_wallet:
                raise AlreadyExists("You already have a wallet for this particular currency")
            new_wallet = Wallet(user_id=user_id, currency=currency, balance=0)
            db.session.add(new_wallet)
            db.session.commit()
            return new_wallet.to_dict()
        except MissingProperties:
            raise
        except AlreadyExists:
            raise
        except KeyError:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
    
    def get_wallet_by_currency(self, user_id, currency):
        return Wallet.query.filter_by(user_id=user_id, currency=currency).first()
    
    def delete_wallet(self, user_id, wallet_id):
        try:
            if not wallet_id:
                raise MissingProperties("You did not provide a wallet Id")
            wallet = Wallet.query.filter_by(id=wallet_id, user_id=user_id).first()
            if not wallet:
                raise DataNotFound("We could not find the wallet with the specified ID", ErrorStatuses.WALLET_NOT_FOUND.value)
            if wallet.balance > 1:
                raise ValueError("Cannot delete a wallet with balance in it. Try closing the wallet instead") 
            db.session.delete(wallet)
            db.session.commit()
            return {"message": "Wallet deleted successfully"}
        except MissingProperties:
            raise
        except DataNotFound:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
        
    
    def transfer_funds(self, from_wallet_id, to_wallet_id, amount, user_id):
        try:
            if not from_wallet_id or not to_wallet_id or not amount:
                raise MissingProperties("Missing sender/receiver wallet Id or amount")
            from_wallet_id = validate_wallet_id(from_wallet_id, "sender wallet id")
            to_wallet_id = validate_wallet_id(to_wallet_id, "receiver wallet id")
            if from_wallet_id == to_wallet_id:
                raise ValueError("Sender and Receivers wallet id cannot be the same")
            # Reject non-numeric, negative, zero, and NaN/inf amounts. A negative
            # amount would otherwise flip the subtraction below into a self-credit
            # while debiting the recipient (theft).
            amount = validate_positive_number(amount, "amount")

            # Lock both wallet rows for the transfer, always in ascending id order
            # so concurrent transfers between the same pair can't deadlock.
            locked_wallets = {
                w.id: w
                for w in Wallet.query.filter(Wallet.id.in_([from_wallet_id, to_wallet_id]))
                .order_by(Wallet.id)
                .with_for_update()
                .all()
            }
            from_wallet = locked_wallets.get(from_wallet_id)
            to_wallet = locked_wallets.get(to_wallet_id)

            if not from_wallet or not to_wallet:
                raise DataNotFound("Invalid wallet Id entered. Confirm both the Sender and Receiver's wallet IDs", ErrorStatuses.WALLET_NOT_FOUND.value)
            if int(from_wallet.user_id) != int(user_id):
                raise DataNotFound("We could not find the wallet you entered", ErrorStatuses.WALLET_NOT_FOUND.value)
            # If the sender's wallet balance is less than the amount to be transferred, return error
            if from_wallet.balance < amount:
                raise InsufficientFunds("Insufficient funds in the source wallet")
            converted_amount = amount
            
            # If currencies are different, get exchange rate and convert from senders currency to receivers currency
            if from_wallet.currency != to_wallet.currency:
                rate = self.get_exchange_rate(from_wallet.currency, to_wallet.currency)
                if not rate:
                    raise DataNotFound("Exchange rate not available")
                converted_amount = amount * rate
            
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
        except DataNotFound:
            raise
        except InsufficientFunds:
            raise
        except MissingProperties:
            raise
        except ValueError:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
        