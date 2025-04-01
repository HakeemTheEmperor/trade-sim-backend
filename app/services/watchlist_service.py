from app.models.watch_list import WatchList
from app.models.stock_available import AvailableStocks
from app.models.stock_price import StockPrice
from ..custom_exceptions import AlreadyExists, DataNotFound, LimitReached, MissingProperties
from .. import db

class WatchlistService:
    def add_to_watchlist(self,user_id, symbol):
        try:
            if not symbol:
                raise MissingProperties("Your request could not be processed as there is a missing stock symbol")
            
            stock = AvailableStocks.query.filter_by(symbol=symbol).first()
            if not stock:
                raise DataNotFound("No stock found for this stock symbol")
            watchlist_count = WatchList.query.filter_by(user_id=user_id).count()
            if watchlist_count >= 5:
                raise LimitReached("You have reached the maximum allowed number of items in your watchlist")
            watchlist_entry = WatchList.query.filter_by(user_id=user_id, stock_symbol=symbol).first()
            if watchlist_entry:
                raise AlreadyExists("The item you are trying to add already exists in the watchlist")
            new_watchlist = WatchList(
                user_id=user_id, 
                stock_symbol=symbol
            )
            db.session.add(new_watchlist)
            db.session.commit()
            return {"message": "Stock successfully added to watchlist", "data": []}
        except DataNotFound:
            raise
        except LimitReached:
            raise
        except AlreadyExists:
            raise
        except MissingProperties:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")

    def get_from_watchlist(self, user_id):
        try:
            watchlist = (
                db.session.query(
                    WatchList.id,
                    AvailableStocks.symbol,
                    AvailableStocks.company_name,
                    AvailableStocks.image,
                    StockPrice.current_price,
                    StockPrice.percentage_change,
                )
                .join(WatchList, WatchList.stock_symbol == AvailableStocks.symbol)
                .join(StockPrice, StockPrice.symbol == AvailableStocks.symbol)
                .filter(WatchList.user_id == user_id)
                .order_by(WatchList.created_at.desc())
                .all()
            )
            if not watchlist:
                raise DataNotFound("No item in your watchlist. Try adding some")
            return [
                {
                "id": item.id,
                "symbol": item.symbol,
                "company_name": item.company_name,
                "image": item.image,
                "price": float(item.current_price),
                "pc": float(item.percentage_change),
                } 
                for item in watchlist
            ]
        except DataNotFound:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")

    def remove_from_watchlist(self, user_id, symbol):
        try:
            watchlist_entry = WatchList.query.filter_by(user_id=user_id, stock_symbol=symbol).first()
            if not watchlist_entry:
                raise DataNotFound("The item you are trying to delete from your watchlist currently does not exist")
            db.session.delete(watchlist_entry)
            db.session.commit()
            
            return {"message": "Stock successfully removed from watchlist", "data": []}
        except DataNotFound:
            raise        
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
    
    def is_in_watchlist(self, user_id, symbol):
        try:
            exists = (
                db.session.query(WatchList)
                .filter_by(user_id=user_id, stock_symbol=symbol)
                .first()
            )
            return exists is not None
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")