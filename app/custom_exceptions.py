class CustomError(Exception):
    pass

class MissingProperties(CustomError):
    def __init__(self, message="Your request could not be processed as certain properties are missing"):
        self.message = message
        super().__init__(self.message)
        
class WalletNotFound(CustomError):
    def __init__(self, message="We could not find the wallet specified. Contact support if you think a mistake has been made"):
        self.message = message
        super().__init__(self.message)
        
class AlreadyExists(CustomError):
    def __init__(self, message="The data you are trying to create already exists"):
        self.message = message
        super().__init__(self.message)

class DataNotFound(CustomError):
    def __init__(self, message="The data you were looking for was not found"):
        self.message = message
        super().__init__(self.message)

class InsufficientFunds(CustomError):
    def __init__(self, message="You lack the required funds to complete this transactions"):
        self.message = message
        super().__init__(self.message)