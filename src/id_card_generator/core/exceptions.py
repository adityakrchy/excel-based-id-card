"""Domain-specific exceptions."""


class IDCardGeneratorError(Exception):
    """Base exception for all application errors."""
    pass


class DataSourceError(IDCardGeneratorError):
    """Raised when loading or validating a data source fails."""
    pass


class SheetNotFoundError(DataSourceError):
    """Raised when the specified worksheet is not found."""
    pass


class PhotoMatchingError(IDCardGeneratorError):
    """Raised when matching photos encounters an error."""
    pass


class AmbiguousPhotoError(PhotoMatchingError):
    """Raised when multiple photos match the same identifier."""
    pass


class TemplateValidationError(IDCardGeneratorError):
    """Raised when template definition is invalid or corrupted."""
    pass


class AssetNotFoundError(TemplateValidationError):
    """Raised when a template references a missing asset."""
    pass


class RenderingError(IDCardGeneratorError):
    """Raised when image or text rendering fails."""
    pass


class FontLoadError(RenderingError):
    """Raised when a requested font cannot be loaded."""
    pass


class GenerationError(IDCardGeneratorError):
    """Raised when batch card generation fails."""
    pass


class ExportError(IDCardGeneratorError):
    """Raised when exporting generated cards or manifests fails."""
    pass


class ProjectError(IDCardGeneratorError):
    """Raised when project file saving, loading, or relinking fails."""
    pass
