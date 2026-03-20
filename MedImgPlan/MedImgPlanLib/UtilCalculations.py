"""
MIT License

Copyright (c) 2022 Yihao Liu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
import numpy


def mat2quat(R):
    if R[0][0] + R[1][1] + R[2][2] > 0:
        qw = math.sqrt(1.0 + R[0][0] + R[1][1] + R[2][2]) / 2.0 * 4.0
        x = (R[2][1] - R[1][2]) / qw
        y = (R[0][2] - R[2][0]) / qw
        z = (R[1][0] - R[0][1]) / qw
        # print(x,y,z,qw)
        return [x, y, z, qw / 4]
    elif (R[0][0] > R[1][1]) and (R[0][0] > R[2][2]):
        s = math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2.0
        qw = (R[2][1] - R[1][2]) / s
        qx = 0.25 * s
        qy = (R[0][1] + R[1][0]) / s
        qz = (R[0][2] + R[2][0]) / s
        return [qx, qy, qz, qw]
    elif R[1][1] > R[2][2]:
        s = math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2.0
        qw = (R[0][2] - R[2][0]) / s
        qx = (R[0][1] + R[1][0]) / s
        qy = 0.25 * s
        qz = (R[1][2] + R[2][1]) / s
        return [qx, qy, qz, qw]
    else:
        s = math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2.0
        qw = (R[1][0] - R[0][1]) / s
        qx = (R[0][2] + R[2][0]) / s
        qy = (R[1][2] + R[2][1]) / s
        qz = 0.25 * s
        return [qx, qy, qz, qw]


def rotx(a):
    return [
        [1.0, 0.0, 0.0],
        [0.0, math.cos(a), -math.sin(a)],
        [0.0, math.sin(a), math.cos(a)],
    ]


def roty(a):
    return [
        [math.cos(a), 0.0, math.sin(a)],
        [0.0, 1.0, 0.0],
        [-math.sin(a), 0.0, math.cos(a)],
    ]


def rotz(a):
    return [
        [math.cos(a), -math.sin(a), 0.0],
        [math.sin(a), math.cos(a), 0.0],
        [0.0, 0.0, 1.0],
    ]


def quat2mat(q):
    qx = q[0]
    qy = q[1]
    qz = q[2]
    qw = q[3]
    mat = [
        [
            1 - 2 * qy * qy - 2 * qz * qz,
            2 * qx * qy - 2 * qz * qw,
            2 * qx * qz + 2 * qy * qw,
        ],
        [
            2 * qx * qy + 2 * qz * qw,
            1 - 2 * qx * qx - 2 * qz * qz,
            2 * qy * qz - 2 * qx * qw,
        ],
        [
            2 * qx * qz - 2 * qy * qw,
            2 * qy * qz + 2 * qx * qw,
            1 - 2 * qx * qx - 2 * qy * qy,
        ],
    ]
    return mat


def normvec3(a):
    return math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)


def transp(A):
    A_ = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    for i in [0, 1, 2]:
        for j in [0, 1, 2]:
            A_[i][j] = A[j][i]
    return A_


def crossProduct(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def utilPosePlan(a, b, c, p, override_y=None):
    """
    Utility function that returns the orientation defined by 3
    points a, b, c, where the point c (or override_y) is the the
    direction of x-axis, and z-axis is perpendicular to a-b-c plane.
    p is the origin of the output pose.
    NOTE: 3D slicer flips x and y axes when loading a model, so the
    directions can be displayed as flipped when showing
    Output is a rotation matrix.
    """
    n = crossProduct(
        [b[0] - a[0], b[1] - a[1], b[2] - a[2]], [b[0] - c[0], b[1] - c[1], b[2] - c[2]]
    )
    nrm = normvec3(n)
    n = [-n[0] / nrm, -n[1] / nrm, -n[2] / nrm]
    if override_y is not None:
        x = crossProduct(
            [override_y[0] - p[0], override_y[1] - p[1], override_y[2] - p[2]], n
        )
    else:
        x = crossProduct([c[0] - p[0], c[1] - p[1], c[2] - p[2]], n)
    nrm = normvec3(x)
    x = [x[0] / nrm, x[1] / nrm, x[2] / nrm]
    y = crossProduct(n, x)
    nrm = normvec3(y)
    y = [y[0] / nrm, y[1] / nrm, y[2] / nrm]
    return transp([x, y, n])


def computeScalarFromDistance(distances, mep, MAX_MEP):
    """
    Compute a scalar value from a distance value based on the maximum distance.
    The scalar value is normalized to the range [0, 1].

    Parameters:
    ---
    distances (numpy.ndarray): The distance values.
    mep (float): The current MEP responce.
    MAX_MEP (float): The maximum poissible MEP response.

    Returns:
    ---
    scalars (numpy.ndarray): The normalized scalar values.
    """
    cutoff_distance = 3.8  # set a cutoff distance as 5 mm above the minimum distance
    distances = distances - numpy.min(distances)

    scalars = (mep / MAX_MEP) * numpy.exp(
        -(distances**2) / (2 * (cutoff_distance / 2) ** 2)
    )
    # for the out-of-range distances, set the scalar to 0
    scalars[distances > cutoff_distance] = 0.0

    return scalars
