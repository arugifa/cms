from pathlib import Path, PurePath
from typing import Any, Dict, List, Mapping, Set, Union

from arugifa.cms.exceptions import FileProcessingError, SourceParsingError
# FIXME: circular import (03/2020)
# from arugifa.cms.handlers import BaseFileHandler


# Content

SourceFilePath = Union[Path, PurePath]


# Content Management

Content = Union[Any, List[Any]]
ContentDeletionResult = List[SourceFilePath]
ContentHandlers = Mapping[str, 'BaseFileHandler']
ContentOperationResult = Dict[str, Any]
ContentOperationErrors = Dict[str, Exception]
ContentUpdateErrors = Dict[str, Union[Dict[str, Exception], List[Exception]]]
ContentUpdatePlan = Dict[str, List[Path]]
ContentUpdatePlanErrors = List[Exception]
ContentUpdateResult = Dict[str, Dict[str, Content]]


# File Processing

FileProcessingResult = Dict[str, Any]
FileProcessingErrors = Set[Union[FileProcessingError, SourceParsingError]]


# Source Parsing

SourceParsingErrors = Set[SourceParsingError]
