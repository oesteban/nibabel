# emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the NiBabel package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import numpy as np
from collections import namedtuple as nt

from ..optpkg import optional_package
from ..viewers import OrthoSlicer3D

from numpy.testing.decorators import skipif

from nose.tools import assert_raises

plt, has_mpl = optional_package('matplotlib.pyplot')[:2]
needs_mpl = skipif(not has_mpl, 'These tests need matplotlib')


@needs_mpl
def test_viewer():
    # Test viewer
    a = np.sin(np.linspace(0, np.pi, 20))
    b = np.sin(np.linspace(0, np.pi*5, 30))
    data = (np.outer(a, b)[..., np.newaxis] * a)[:, :, :, np.newaxis]
    data = data * np.array([1., 2.])  # give it a # of volumes > 1
    v = OrthoSlicer3D(data)
    plt.draw()

    # fake some events, inside and outside axes
    v._on_scroll(nt('event', 'button inaxes key')('up', None, None))
    for ax in (v._axes['x'], v._axes['v']):
        v._on_scroll(nt('event', 'button inaxes key')('up', ax, None))
    v._on_scroll(nt('event', 'button inaxes key')('up', ax, 'shift'))
    # "click" outside axes, then once in each axis, then move without click
    v._on_mouse(nt('event', 'xdata ydata inaxes button')(0.5, 0.5, None, 1))
    for ax in v._axes.values():
        v._on_mouse(nt('event', 'xdata ydata inaxes button')(0.5, 0.5, ax, 1))
    v._on_mouse(nt('event', 'xdata ydata inaxes button')(0.5, 0.5, None, None))
    v.close()

    # non-multi-volume
    v = OrthoSlicer3D(data[:, :, :, 0])
    v._on_scroll(nt('event', 'button inaxes key')('up', v._axes['x'], 'shift'))
    v._on_keypress(nt('event', 'key')('escape'))

    # other cases
    fig, axes = plt.subplots(1, 4)
    plt.close(fig)
    OrthoSlicer3D(data, pcnt_range=[0.1, 0.9], axes=axes)
    OrthoSlicer3D(data, axes=axes[:3])
    assert_raises(ValueError, OrthoSlicer3D, data[:, :, 0, 0])
    assert_raises(ValueError, OrthoSlicer3D, data, affine=np.eye(3))
