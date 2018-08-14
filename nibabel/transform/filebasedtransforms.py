# emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the NiBabel package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
''' Common interface for any image format--volume or surface, binary or xml.'''

from copy import deepcopy
from six import string_types
from .fileholders import FileHolder
from .filename_parser import (types_filenames, TypesFilenamesError,
                              splitext_addext)
from .openers import ImageOpener


class TransformFileError(Exception):
    pass


class FileBasedTransform(object):
    '''
    Abstract image class with interface for loading/saving transforms from disk.

    The class doesn't define any image properties.

    It has:

    attributes:

       * extra

    properties:

       * shape
       * header

    methods:

       * .to_filename(fname) - writes data to filename(s) derived from
         ``fname``, where the derivation may differ between formats.

    classmethods:

       * from_filename(fname) - make instance by loading from filename
       * instance_to_filename(img, fname) - save ``img`` instance to
         filename ``fname``.

    **There are several ways of writing data**

    There is the usual way, which is the default::

        xfm.to_filename(fname)

    and that is, to take the data encapsulated by the transform and cast it
    to the datatype the header expects.

    You can load a transform from file with::

       xfm.from_filename(fname)

    '''
    __slots__ = ['_meta_sniff_len', 'valid_exts', '_compressed_suffixes',
                 '_filename']

    def __init__(self):
        ''' Initialize transform file'''

        self._meta_sniff_len = 0
        self.valid_exts = ()
        self._compressed_suffixes = ()
        self._filename = None

    def __getitem__(self, key):
        ''' No slicing or dictionary interface for images
        '''
        raise TypeError("Cannot slice transform objects.")

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        if not self.__class__.check_filename(value):
            raise TransformFileError(
                'Filespec "{0}" does not look right for class {1}'.format(
                    value, self))
        self._filename = value

    @classmethod
    def from_filename(klass, filename):
        raise NotImplementedError

    @classmethod
    def check_filename(klass, filename):
        raise NotImplementedError

    def to_filename(self, filename):
        ''' Write transform to disk

        Parameters
        ----------
        filename : str
           filename to which to save the transform.

        Returns
        -------
        None
        '''
        raise NotImplementedError

    load = from_filename

    @classmethod
    def instance_to_filename(klass, xfm, filename):
        ''' Save `xfm` in our own format, to name implied by `filename`

        This is a class method

        Parameters
        ----------
        xfm : ``any FileBasedTransform`` instance

        filename : str
           Filename, implying name to which to save image.
        '''
        xfm = klass.from_xfm(xfm)
        xfm.to_filename(filename)

    @classmethod
    def from_xfm(klass, xfm):
        ''' Class method to create new instance of own class from `xfm`

        Parameters
        ----------
        xfm : ``FileBasedTransform`` instance.

        Returns
        -------
        transform : ``FileBasedTransform`` instance
           Image, of our own class
        '''
        raise NotImplementedError()

    @classmethod
    def _sniff_meta_for(klass, filename, sniff_nbytes, sniff=None):
        """ Sniff metadata for image represented by `filename`

        Parameters
        ----------
        filename : str
            Filename for an image, or an image header (metadata) file.
            If `filename` points to an image data file, and the image type has
            a separate "header" file, we work out the name of the header file,
            and read from that instead of `filename`.
        sniff_nbytes : int
            Number of bytes to read from the image or metadata file
        sniff : (bytes, fname), optional
            The result of a previous call to `_sniff_meta_for`.  If fname
            matches the computed header file name, `sniff` is returned without
            rereading the file.

        Returns
        -------
        sniff : None or (bytes, fname)
            None if we could not read the image or metadata file.  `sniff[0]`
            is either length `sniff_nbytes` or the length of the image /
            metadata file, whichever is the shorter. `fname` is the name of
            the sniffed file.
        """
        froot, ext, trailing = splitext_addext(filename,
                                               klass._compressed_suffixes)
        # Determine the metadata location
        t_fnames = types_filenames(
            filename,
            klass.files_types,
            trailing_suffixes=klass._compressed_suffixes)
        meta_fname = t_fnames.get('header', filename)

        # Do not re-sniff if it would be from the same file
        if sniff is not None and sniff[1] == meta_fname:
            return sniff

        # Attempt to sniff from metadata location
        try:
            with ImageOpener(meta_fname, 'rb') as fobj:
                binaryblock = fobj.read(sniff_nbytes)
        except IOError:
            return None
        return (binaryblock, meta_fname)

    @classmethod
    def path_maybe_image(klass, filename, sniff=None, sniff_max=1024):
        """ Return True if `filename` may be image matching this class

        Parameters
        ----------
        filename : str
            Filename for an image, or an image header (metadata) file.
            If `filename` points to an image data file, and the image type has
            a separate "header" file, we work out the name of the header file,
            and read from that instead of `filename`.
        sniff : None or (bytes, filename), optional
            Bytes content read from a previous call to this method, on another
            class, with metadata filename.  This allows us to read metadata
            bytes once from the image or header, and pass this read set of
            bytes to other image classes, therefore saving a repeat read of the
            metadata.  `filename` is used to validate that metadata would be
            read from the same file, re-reading if not.  None forces this
            method to read the metadata.
        sniff_max : int, optional
            The maximum number of bytes to read from the metadata.  If the
            metadata file is long enough, we read this many bytes from the
            file, otherwise we read to the end of the file.  Longer values
            sniff more of the metadata / image file, making it more likely that
            the returned sniff will be useful for later calls to
            ``path_maybe_image`` for other image classes.

        Returns
        -------
        maybe_image : bool
            True if `filename` may be valid for an image of this class.
        sniff : None or (bytes, filename)
            Read bytes content from found metadata.  May be None if the file
            does not appear to have useful metadata.
        """
        froot, ext, trailing = splitext_addext(filename,
                                               klass._compressed_suffixes)
        if ext.lower() not in klass.valid_exts:
            return False, sniff
        if not hasattr(klass.header_class, 'may_contain_header'):
            return True, sniff

        # Force re-sniff on too-short sniff
        if sniff is not None and len(sniff[0]) < klass._meta_sniff_len:
            sniff = None
        sniff = klass._sniff_meta_for(filename,
                                      max(klass._meta_sniff_len, sniff_max),
                                      sniff)
        if sniff is None or len(sniff[0]) < klass._meta_sniff_len:
            return False, sniff
        return klass.header_class.may_contain_header(sniff[0]), sniff
