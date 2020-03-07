from pathlib import Path, PurePath
from typing import Any, Dict, List, Mapping, Set, Union

from arugifa.cms.exceptions import FileProcessingError, SourceParsingError
# FIXME: circular import (03/2020)
# from arugifa.cms.handlers import BaseFileHandler


# Content Management

DatabaseItem = Union[Any, List[Any]]
ContentHandlers = Mapping[str, 'BaseFileHandler']

# Content Update

ContentAdditionResult = Dict[str, Any]
ContentAdditionErrors = Dict[str, Exception]
ContentModificationResult = Dict[str, Any]
ContentModificationErrors = Dict[str, Exception]
ContentRenamingResult = Dict[str, Any]
ContentRenamingErrors = Dict[str, Exception]
ContentDeletionResult = List[PurePath]
ContentDeletionErrors = Dict[str, Exception]

ContentUpdateResult = Dict[str, Dict[str, DatabaseItem]]
ContentUpdateTodo = Dict[str, List[Path]]


# Source Files Processing

FileProcessingResult = Dict[str, Any]
FileProcessingErrors = Set[Union[FileProcessingError, SourceParsingError]]


# Source Files Parsing

SourceParsingErrors = Set[SourceParsingError]
