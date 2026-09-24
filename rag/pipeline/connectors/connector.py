from abc import ABC, abstractmethod

class Connector(ABC):

    @abstractmethod
    def retrieve_data(self) -> list[str]:
        pass
