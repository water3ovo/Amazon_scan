"""Amazon AE/SA scan package."""

__version__ = "2.0.0-beta.5.3"

from .amazon_parser import AmazonParser
from .parser_fixes import apply_parser_fixes

apply_parser_fixes(AmazonParser)
