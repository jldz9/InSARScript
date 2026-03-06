from .registry import Processor, Downloader, Analyzer

class InSAREngine:

    def __init__(
        self,
        downloader=None,
        processor=None,
        analyzer=None,
        config=None
    ):
        self.downloader = downloader
        self.processor = processor
        self.analyzer = analyzer
        self.config = config

    def run(self):

        if self.downloader:
            self.downloader.search()
            self.downloader.download()

        if self.processor:
            self.processor.run()

        if self.analyzer:
            self.analyzer.run()