import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
import requests
from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.exchangerate import ExchangeRate
from ..models.transactions import Transaction, TransactionType, TransactionCategory
from .. import db
from ..custom_exceptions import AlreadyExists, DataNotFound, InsufficientFunds, MissingProperties
from ..utils.enums_utils import ErrorStatuses
from ..utils.validation_utils import validate_positive_number, validate_wallet_id
# Aliased so it doesn't shadow the ExchangeRate *model* imported above.
from ..integrations.providers import ExchangeRate as ExchangeRateAPI

# Never let an outbound call hang a request/worker indefinitely.
REQUEST_TIMEOUT_SECONDS = 10

# Fallback freshness window used only when a cached row has no next_update (e.g.
# a legacy row, or the provider didn't return time_next_update_unix). Normally
# freshness is driven by the provider's own next-update timestamp instead.
EXCHANGE_RATE_TTL_HOURS = int(os.getenv("EXCHANGE_RATE_TTL_HOURS", "24"))

class WalletService:
    def get_exchange_rate(self, from_currency, to_currency):
        if from_currency == to_currency:
            return Decimal(1)

        rate_record = ExchangeRate.query.filter_by(
            base_currency=from_currency, target_currency=to_currency
        ).first()
        if rate_record and self._is_fresh(rate_record):
            return rate_record.rate

        # Stale or missing: one /latest/{from} call refreshes every pair off this
        # base (and their reciprocals), so a single request covers both directions.
        self._refresh_rates(from_currency)

        rate_record = ExchangeRate.query.filter_by(
            base_currency=from_currency, target_currency=to_currency
        ).first()
        if not rate_record:
            raise DataNotFound("Exchange rate not available for this currency pair")
        return rate_record.rate

    def _is_fresh(self, rate_record):
        now = datetime.now(timezone.utc)
        if rate_record.next_update:
            # Fresh until the provider's own next update — refetch right after it.
            return now < rate_record.next_update
        # No next_update on this row: fall back to a fixed TTL from last fetch.
        return rate_record.last_updated > now - timedelta(hours=EXCHANGE_RATE_TTL_HOURS)

    def _refresh_rates(self, base_currency):
        """Fetch /latest/{base_currency} and upsert every supported pair (plus
        the reciprocal of each) so both directions are cached from one call."""
        rates, next_update = self.fetch_latest(base_currency)
        for target in WalletCurrencyType:
            if target == base_currency:
                continue
            if target.value not in rates:
                continue
            rate = Decimal(str(rates[target.value]))
            self._upsert_rate(base_currency, target, rate, next_update)
            # Derive the reverse direction locally instead of spending a call on it.
            if rate > 0:
                self._upsert_rate(target, base_currency, Decimal(1) / rate, next_update)
        db.session.commit()

    def _upsert_rate(self, base, target, rate, next_update):
        now = datetime.now(timezone.utc)
        record = ExchangeRate.query.filter_by(
            base_currency=base, target_currency=target
        ).first()
        if record:
            record.rate = rate
            record.last_updated = now
            record.next_update = next_update
        else:
            db.session.add(ExchangeRate(
                base_currency=base,
                target_currency=target,
                rate=rate,
                last_updated=now,
                next_update=next_update,
            ))

    def fetch_latest(self, base_currency):
        """Return (conversion_rates dict, next_update datetime|None) for a base."""
        try:
            url = ExchangeRateAPI.latest_url(base_currency.value)
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            data = response.json()
            if data.get("result") != "success":
                raise DataNotFound("Failed to fetch exchange rates")
            rates = data.get("conversion_rates", {})
            next_update = None
            ts = data.get("time_next_update_unix")
            if ts:
                next_update = datetime.fromtimestamp(ts, tz=timezone.utc)
            return rates, next_update
        except DataNotFound:
            raise
        except Exception as e:
            raise ValueError(f"Error fetching exchange rates: {str(e)}")
        
        
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
        