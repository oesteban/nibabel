# emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the NiBabel package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
''' Linear transforms '''
from __future__ import division, print_function, absolute_import
import sys
import numpy as np
from scipy import ndimage as ndi

from ..loadsave import load as loadimg
from ..affines import from_matvec, voxel_sizes
from .base import TransformBase


LPS = np.diag([-1, -1, 1, 1])


class Affine(TransformBase):
    '''Represents linear transforms on image data'''
    __slots__ = ['_matrix']

    def __init__(self, matrix=None, reference=None):
        '''Initialize a transform

        Parameters
        ----------

        matrix : ndarray
            The inverse coordinate transformation matrix **in physical
            coordinates**, mapping coordinates from *reference* space
            into *moving* space.
            This matrix should be provided in homogeneous coordinates.

        Examples
        --------

        >>> xfm = Affine([[1, 0, 0, 4], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        >>> xfm.matrix  # doctest: +NORMALIZE_WHITESPACE
        array([[1, 0, 0, 4],
               [0, 1, 0, 0],
               [0, 0, 1, 0],
               [0, 0, 0, 1]])

        '''
        if matrix is None:
            matrix = np.eye(4)

        self._matrix = np.array(matrix)
        assert self._matrix.ndim in (2, 3), 'affine matrix should be 2D or 3D'
        assert self._matrix.shape[0] == self._matrix.shape[1], 'affine matrix is not square'
        super(Affine, self).__init__()

        if reference:
            self.reference = reference

    @property
    def matrix(self):
        return self._matrix

    def resample(self, moving, order=3, mode='constant', cval=0.0, prefilter=True,
                 output_dtype=None):
        '''Resample the moving image in reference space

        Parameters
        ----------

        moving : `spatialimage`
            The image object containing the data to be resampled in reference
            space
        order : int, optional
            The order of the spline interpolation, default is 3.
            The order has to be in the range 0-5.
        mode : {'reflect', 'constant', 'nearest', 'mirror', 'wrap'}, optional
            Determines how the input image is extended when the resamplings overflows
            a border. Default is 'constant'.
        cval : float, optional
            Constant value for ``mode='constant'``. Default is 0.0.
        prefilter: bool, optional
            Determines if the moving image's data array is prefiltered with
            a spline filter before interpolation. The default is ``True``,
            which will create a temporary *float64* array of filtered values
            if *order > 1*. If setting this to ``False``, the output will be
            slightly blurred if *order > 1*, unless the input is prefiltered,
            i.e. it is the result of calling the spline filter on the original
            input.

        Returns
        -------

        moved_image : `spatialimage`
            The moving imaged after resampling to reference space.


        Examples
        --------

        >>> import nibabel as nib
        >>> xfm = Affine([[1, 0, 0, 4], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        >>> ref = nib.load('image.nii.gz')
        >>> xfm.reference = ref
        >>> xfm.resample(ref, order=0)

        '''
        if output_dtype is None:
            output_dtype = moving.header.get_data_dtype()

        try:
            reference = self.reference
        except ValueError:
            print('Warning: no reference space defined, using moving as reference',
                  file=sys.stderr)
            reference = moving

        # Compose an index to index affine matrix
        matrix = np.linalg.inv(moving.affine).dot(self._matrix.dot(reference.affine))
        mdata = moving.get_data()
        moved = ndi.affine_transform(
            mdata, matrix=matrix[:mdata.ndim, :mdata.ndim],
            offset=matrix[:mdata.ndim, mdata.ndim],
            output_shape=reference.shape, order=order, mode=mode,
            cval=cval, prefilter=prefilter)

        moved_image = moving.__class__(moved, reference.affine, moving.header)
        moved_image.header.set_data_dtype(output_dtype)

        return moved_image

    def map_point(self, coords, forward=True):
        coords = np.array(coords)
        if coords.shape[0] == self._matrix.shape[0] - 1:
            coords = np.append(coords, [1])
        affine = self._matrix if forward else np.linalg.inv(self._matrix)
        return affine.dot(coords)[:-1]

    def map_voxel(self, index, moving=None):
        try:
            reference = self.reference
        except ValueError:
            print('Warning: no reference space defined, using moving as reference',
                  file=sys.stderr)
            reference = moving
        else:
            if moving is None:
                moving = reference
        finally:
            if reference is None:
                raise ValueError('Reference and moving spaces are both undefined')

        index = np.array(index)
        if index.shape[0] == self._matrix.shape[0] - 1:
            index = np.append(index, [1])

        matrix = reference.affine.dot(self._matrix.dot(np.linalg.inv(moving.affine)))
        return tuple(matrix.dot(index)[:-1])

    def _to_hdf5(self, x5_root):
        x5_root.create_dataset('Transform', data=self._matrix[:3, :])
        x5_root.create_dataset('Inverse', data=np.linalg.inv(self._matrix)[:3, :])
        x5_root['Type'] = 'affine'

        if self._reference:
            self.reference._to_hdf5(x5_root.create_group('Reference'))

    def to_filename(self, filename, fmt='X5', moving=None):
        '''Store the transform in BIDS-Transforms HDF5 file format (.x5).
        '''

        if fmt.lower() in ['itk', 'ants', 'elastix', 'nifty']:
            parameters = LPS.dot(self.matrix.dot(LPS))
            parameters = parameters[:3, :3].reshape(-1).tolist() + parameters[:3, 3].tolist()
            itkfmt = """\
#Insight Transform File V1.0
#Transform 0
Transform: MatrixOffsetTransformBase_double_3_3
Parameters: {}
FixedParameters: 0 0 0\n""".format
            with open(filename, 'w') as f:
                f.write(itkfmt(' '.join(['%g' % p for p in parameters])))
            return filename

        if fmt.lower() == 'afni':
            parameters = LPS.dot(self.matrix.dot(LPS))
            parameters = parameters[:3, :].reshape(-1).tolist()
            np.savetxt(filename, np.atleast_2d(parameters),
                       delimiter='\t', header="""\
3dvolreg matrices (DICOM-to-DICOM, row-by-row):""")
            return filename

        if fmt.lower() == 'fsl':
            if not moving:
                moving = self.reference

            if isinstance(moving, str):
                moving = loadimg(moving)

            # Adjust for reference image offset and orientation
            refswp, refspc = _fsl_aff_adapt(self.reference)
            pre = self.reference.affine.dot(
                np.linalg.inv(refspc).dot(np.linalg.inv(refswp)))

            # Adjust for moving image offset and orientation
            movswp, movspc = _fsl_aff_adapt(moving)
            post = np.linalg.inv(movswp).dot(movspc.dot(np.linalg.inv(
                moving.affine)))

            # Compose FSL transform
            mat = np.linalg.inv(post.dot(self.matrix.dot(pre)))
            np.savetxt(filename, mat, delimiter=' ', fmt='%g')
            return filename
        return super(Affine, self).to_filename(filename, fmt=fmt)


def load(filename, fmt='X5', reference=None):
    ''' Load a linear transform '''

    if fmt.lower() in ['itk', 'ants', 'elastix', 'nifty']:
        with open(filename) as itkfile:
            itkxfm = itkfile.read().splitlines()

        parameters = np.fromstring(itkxfm[3].split(':')[-1].strip(), dtype=float, sep=' ')
        offset = np.fromstring(itkxfm[4].split(':')[-1].strip(), dtype=float, sep=' ')
        if len(parameters) == 12:
            matrix = from_matvec(parameters[:9].reshape((3, 3)), parameters[9:])
            c_neg = from_matvec(np.eye(3), offset * -1.0)
            c_pos = from_matvec(np.eye(3), offset)
            matrix = LPS.dot(c_pos.dot(matrix.dot(c_neg.dot(LPS))))

    # if fmt.lower() == 'afni':
    #     parameters = LPS.dot(self.matrix.dot(LPS))
    #     parameters = parameters[:3, :].reshape(-1).tolist()

    if reference and isinstance(reference, str):
        reference = loadimg(reference)
    return Affine(matrix, reference)


def _fsl_aff_adapt(space):
    """Calculates a matrix to convert from the original RAS image
    coordinates to FSL's internal coordinate system of transforms
    """
    aff = space.affine
    zooms = list(voxel_sizes(aff)) + [1]
    swp = np.eye(4)
    if np.linalg.det(aff) > 0:
        swp[0, 0] = -1.0
        swp[0, 3] = (space.shape[0] - 1) * zooms[0]
    return swp, np.diag(zooms)
