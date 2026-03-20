"""
MIT License

Copyright (c) 2022 Yihao Liu, Johns Hopkins University

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

import slicer, vtk
from MedImgPlanLib.UtilSlicerFuncs import setColorTextByDistance, setTranslation
from MedImgPlanLib.UtilConnectionsWtNnBlcRcv import UtilConnectionsWtNnBlcRcv

#
# Use UtilConnectionsWtNnBlcRcv and override the data handler
#


class MedImgConnections(UtilConnectionsWtNnBlcRcv):

    def __init__(self, configPath, modulesufx):
        super().__init__(configPath, modulesufx)
        self._transformMatrixPointOnMesh = None
        self._pointOnMeshIndicator = None
        self._transformMatrixPointPtrtip = None
        self._pointPtrtipIndicator = None

    def setup(self):
        super().setup()
        self._view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        if not self._transformMatrixPointPtrtip:
            self._transformMatrixPointPtrtip = vtk.vtkMatrix4x4()
        if not self._transformMatrixPointOnMesh:
            self._transformMatrixPointOnMesh = vtk.vtkMatrix4x4()

    def handleReceivedData(self):
        """
        Override the parent class function
        """
        self.utilMsgParse()

    def utilMsgParse(self):
        """
        Msg format: 
            1. TRE check
                "__msg_point_0000.00000_0000.00000_0000.00000"
                x, y, z in mm
            2. plan tool pose points
                "__msg_toolpose_0000.00000_0000.00000_0000.00000_0000.00000_0000.00000_0000.00000"
                x1, y1, z1 in mm
                x2, y2, z2 in mm
        """
        data = self._data_buff.decode("UTF-8")
        if data.startswith('__msg_point_'):
            msg = data[12:]
            num_str = msg.split("_")
            num = []
            for i in num_str:
                num.append(float(i))
            self.utilTRECheckCallback(num)
        if data.startswith('__msg_toolpose_'):
            print(data)
            msg = data[15:]
            num_str = msg.split("_")
            p1 = [float(num_str[0]),float(num_str[1]),float(num_str[2])]
            p2 = [float(num_str[3]),float(num_str[4]),float(num_str[5])]
            point_list_node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
            point_list_node.AddControlPoint(p1[0], p1[1], p1[2], 't1')
            point_list_node.AddControlPoint(p2[0], p2[1], p2[2], 't2')
            point_list_node.SetName('Received')

    def utilTRECheckCallback(self, p):
        """
        Called each time when a valid point message is received
        """
        inModel = self._parameterNode.GetNodeReference("InputMeshSkin")
        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet(inModel.GetPolyData())
        pointLocator.BuildLocator()
        closest_point = pointLocator.FindClosestPoint(p)
        p_closest = inModel.GetPolyData().GetPoint(closest_point)

        setTranslation(p, self._transformMatrixPointPtrtip)
        setTranslation(p_closest, self._transformMatrixPointOnMesh)

        self._parameterNode.GetNodeReference(
            "PointPtrtipTr").SetMatrixTransformToParent(self._transformMatrixPointPtrtip)
        self._parameterNode.GetNodeReference(
            "PointOnMeshTr").SetMatrixTransformToParent(self._transformMatrixPointOnMesh)

        setColorTextByDistance(
            self._view, p_closest, p, self._colorchangethresh,
            self._pointOnMeshIndicator,
            self._pointPtrtipIndicator)

        slicer.app.processEvents()
