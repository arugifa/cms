from abc import ABC, abstractmethod


class BaseTransaction(ABC):
    @abstractmethod
    def commit(self):
        pass

    @abstractmethod
    def rollback(self):
        pass
