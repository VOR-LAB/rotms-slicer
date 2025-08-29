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

import os, json, logging, math, random, yaml, numpy, datetime
import vtk, qt, ctk, slicer

from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from MedImgPlanLib.UtilFormat import utilNumStrFormat
from MedImgPlanLib.UtilCalculations import (
    mat2quat,
    utilPosePlan,
    rotx,
    roty,
    rotz,
    quat2mat,
    computeScalarFromDistance,
)
from MedImgPlanLib.UtilMedImgConnections import MedImgConnections

from MedImgPlanLib.UtilSlicerFuncs import (
    drawAPlane,
    getRotAndPFromMatrix,
    initModelAndTransform,
    setRotation,
    setTransform,
    setTranslation,
)

#
# MedImgPlanLogic
#


class MedImgPlanLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, configPath):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self._configPath = configPath
        self._connections = MedImgConnections(configPath, "MEDIMG")
        self._connections.setup()
        self._parameterNode = self.getParameterNode()

        with open(self._configPath + "CommandsConfig.json") as f:
            self._commandsData = (json.load(f))["MegImgCmd"]

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("ColorChangeThresh"):
            parameterNode.SetParameter("ColorChangeThresh", "4.0")
        if not parameterNode.GetParameter("ManualAdjustToolPoseRot"):
            parameterNode.SetParameter("ManualAdjustToolPoseRot", "0.0")
        if not parameterNode.GetParameter("ManualAdjustToolPosePos"):
            parameterNode.SetParameter("ManualAdjustToolPosePos", "0.0")
        if not parameterNode.GetParameter("GridDistanceApart"):
            parameterNode.SetParameter("GridDistanceApart", "1.0")
        if not parameterNode.GetParameter("GridPlanNum"):
            parameterNode.SetParameter("GridPlanNum", "16")
        if not parameterNode.GetParameter("TRECalculating"):
            parameterNode.SetParameter("TRECalculating", "false")
        if not parameterNode.GetParameter("PlanOnBrain"):
            parameterNode.SetParameter("PlanOnBrain", "true")
        # if not parameterNode.GetParameter("PlanGridOnAnatomySurf"):
        #     parameterNode.SetParameter("PlanGridOnAnatomySurf", "true")
        if not parameterNode.GetParameter("PlanGridOnPerspPlane"):
            parameterNode.SetParameter("PlanGridOnPerspPlane", "true")
        if not parameterNode.GetParameter("PlanGridOnPerspPlane"):
            parameterNode.SetParameter("PlanGridOnPerspPlane", "false")
        if not parameterNode.GetParameter("ToolRotOption"):
            parameterNode.SetParameter("ToolRotOption", "skinclosest")

    def processStartTRECalculation(self):
        """
        Called when click the start button
        """
        inModel = self._parameterNode.GetNodeReference("InputMeshSkin")
        if not inModel:
            slicer.util.errorDisplay("Please select a image model first!")
            return

        self._parameterNode = self.getParameterNode()
        self._connections._parameterNode = self.getParameterNode()

        with open(self._configPath + "Config.json") as f:
            configData = json.load(f)

        pointOnMeshIndicator = initModelAndTransform(
            self._parameterNode,
            "PointOnMeshTr",
            self._connections._transformMatrixPointOnMesh,
            "PointOnMeshIndicator",
            self._configPath + configData["POINT_INDICATOR_MODEL"],
        )

        pointPtrtipIndicator = initModelAndTransform(
            self._parameterNode,
            "PointPtrtipTr",
            self._connections._transformMatrixPointPtrtip,
            "PointPtrtipIndicator",
            self._configPath + configData["POINT_INDICATOR_MODEL"],
        )

        self._connections._pointOnMeshIndicator = pointOnMeshIndicator
        self._connections._pointPtrtipIndicator = pointPtrtipIndicator

        self._connections._colorchangethresh = float(
            self._parameterNode.GetParameter("ColorChangeThresh")
        )
        self._connections._flag_receiving_nnblc = True
        self._connections.receiveTimerCallBack()

    def processStopTRECalculation(self):

        self._connections._flag_receiving_nnblc = False

    def processVisFRE(self, pathDigLandmarks, pathPlanLandmarks, pathRegResult):
        """
        Visualization of the planned landmarks and the digitized landmarks
        """

        # Load digitized landmarks. Convert ROS units to Slicer units
        with open(pathDigLandmarks, "r") as stream:
            try:
                dig = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                return
        numDig, dig_ = dig["NUM"], []
        for i in range(numDig):
            dig_.append(
                [
                    dig["DIGITIZED"]["d" + str(i)]["x"] * 1000.0,
                    dig["DIGITIZED"]["d" + str(i)]["y"] * 1000.0,
                    dig["DIGITIZED"]["d" + str(i)]["z"] * 1000.0,
                ]
            )
        dig_ = numpy.array(dig_).transpose()

        # Load registered results. Convert ROS units to Slicer units
        with open(pathRegResult, "r") as stream:
            try:
                reg = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                return
        rot = [
            reg["ROTATION"]["x"],
            reg["ROTATION"]["y"],
            reg["ROTATION"]["z"],
            reg["ROTATION"]["w"],
        ]
        rot = quat2mat(rot)
        p = [reg["TRANSLATION"]["x"], reg["TRANSLATION"]["y"], reg["TRANSLATION"]["z"]]
        rot_ = numpy.array(rot).transpose()
        p_ = -numpy.matmul(rot_, numpy.array(p).reshape((3, 1))) * 1000.0

        # Get aligned point cloud and visualize
        res = numpy.matmul(rot_, dig_) + p_
        if self._parameterNode.GetNodeReference("AlignedLandmarks"):
            markupsNode = self._parameterNode.GetNodeReference("AlignedLandmarks")
            slicer.mrmlScene.RemoveNode(markupsNode)
        markupsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "Aligned"
        )
        self._parameterNode.SetNodeReferenceID("AlignedLandmarks", markupsNode.GetID())
        slicer.modules.markups.logic().SetActiveList(markupsNode)

        for i in res.transpose():
            slicer.modules.markups.logic().AddControlPoint(i[0], i[1], i[2])

        markupsNode.GetDisplayNode().SetSelectedColor(0, 1, 0)
        markupsNode.GetDisplayNode().SetTextScale(0)

        # Load planned landmarks. Convert ROS units to Slicer units
        if pathDigLandmarks:
            with open(pathPlanLandmarks, "r") as stream:
                try:
                    plan = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    print(exc)
                    return
            numPlan, plan_ = plan["NUM"], []
            if numDig != numPlan:
                slicer.util.errorDisplay(
                    "The number of digitized landmarks does not match the number of planned landmarks!"
                )
                return
            for i in range(numPlan):
                plan_.append(
                    [
                        plan["PLANNED"]["p" + str(i)]["x"] * 1000.0,
                        plan["PLANNED"]["p" + str(i)]["y"] * 1000.0,
                        plan["PLANNED"]["p" + str(i)]["z"] * 1000.0,
                    ]
                )
            plan_ = numpy.array(plan_).transpose()

            # visualize
            if self._parameterNode.GetNodeReference("AlignedLandmarksPlanned"):
                markupsNode = self._parameterNode.GetNodeReference(
                    "AlignedLandmarksPlanned"
                )
                slicer.mrmlScene.RemoveNode(markupsNode)
            markupsNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode", "Plan"
            )
            self._parameterNode.SetNodeReferenceID(
                "AlignedLandmarksPlanned", markupsNode.GetID()
            )
            slicer.modules.markups.logic().SetActiveList(markupsNode)
            markupsNode.GetDisplayNode().SetSelectedColor(0, 0, 1)
            markupsNode.GetDisplayNode().SetTextScale(0)
            for i in plan_.transpose():
                slicer.modules.markups.logic().AddControlPoint(i[0], i[1], i[2])

        # Print FRE
        slicer.util.infoDisplay(
            "FRE of each landmark: " + str(numpy.linalg.norm(res - plan_, axis=0))
        )

        # Disable control point placement
        slicer.mrmlScene.GetNodeByID(
            "vtkMRMLInteractionNodeSingleton"
        ).SetPlaceModePersistence(0)

    def processVisICP(self, pathICPPoints, pathICPReg, ignoreICP):
        """
        Visualization of the ICP digitization points
        """

        with open(pathICPPoints, "r") as stream:
            try:
                dig_dict = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                return

        dig = []
        for k in dig_dict.keys():
            # convert ROS m unit to mm
            dig.extend([float(i) * 1000.0 for i in dig_dict[k].strip().split(",")[:-1]])

        dig_ = numpy.array(dig).reshape((-1, 3)).transpose()

        # Load registered results. Convert ROS units to Slicer units
        with open(pathICPReg, "r") as stream:
            try:
                reg = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                return
        if int(reg["FLAG_ICP"]) != 1:
            if ignoreICP:
                pass
            else:
                slicer.util.errorDisplay("ICP was not done yet!")
                return

        rot = [
            reg["ROTATION"]["x"],
            reg["ROTATION"]["y"],
            reg["ROTATION"]["z"],
            reg["ROTATION"]["w"],
        ]
        rot = quat2mat(rot)
        p = [reg["TRANSLATION"]["x"], reg["TRANSLATION"]["y"], reg["TRANSLATION"]["z"]]
        rot_ = numpy.array(rot).transpose()
        p_ = -numpy.matmul(rot_, numpy.array(p).reshape((3, 1))) * 1000.0

        if not self._parameterNode.GetNodeReference("TransformICPReg"):
            transformNode = slicer.vtkMRMLTransformNode()
            slicer.mrmlScene.AddNode(transformNode)
            self._parameterNode.SetNodeReferenceID(
                "TransformICPReg", transformNode.GetID()
            )

        transformMatrix = vtk.vtkMatrix4x4()
        setTransform(rot_, p_, transformMatrix)
        targetPoseTransform = self._parameterNode.GetNodeReference("TransformICPReg")
        targetPoseTransform.SetMatrixTransformToParent(transformMatrix)

        # Get aligned point cloud and visualize
        res = numpy.matmul(rot_, dig_) + p_
        if self._parameterNode.GetNodeReference("AlignedICPPointClouds"):
            markupsNode = self._parameterNode.GetNodeReference("AlignedICPPointClouds")
            slicer.mrmlScene.RemoveNode(markupsNode)
        markupsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "AlignedICP"
        )
        self._parameterNode.SetNodeReferenceID(
            "AlignedICPPointClouds", markupsNode.GetID()
        )
        slicer.modules.markups.logic().SetActiveList(markupsNode)
        markupsNode.GetDisplayNode().SetSelectedColor(0, 1, 0)
        markupsNode.GetDisplayNode().SetTextScale(0)

        for i in res.transpose():
            slicer.modules.markups.logic().AddControlPoint(i[0], i[1], i[2])

        # Disable control point placement
        slicer.mrmlScene.GetNodeByID(
            "vtkMRMLInteractionNodeSingleton"
        ).SetPlaceModePersistence(0)

    def processPushPlanLandmarks(self, inputMarkupsNode):
        """
        Send out the markups for registration
        """
        if not inputMarkupsNode:
            slicer.util.errorDisplay("Input markup is invalid!")
            raise ValueError("Input markup is invalid!")
        if inputMarkupsNode.GetNumberOfFiducials() < 3:
            slicer.util.errorDisplay("Input landmarks are less than 3!")
            raise ValueError("Input landmarks are less than 3!")
        self.utilSendLandmarks(-1)

    def processDigHilight(self):
        self.processDigIndividual("START_LANDMARK_DIG_NUM")

    def processDigPrevAndDigHilight(self):
        self.processDigIndividual("START_LANDMARK_DIG_PREV_DIG_HILIGHT")

    def processDigIndividual(self, s):
        if not self._parameterNode.GetParameter("LandmarkWidgetHilightIdx"):
            slicer.util.errorDisplay("Please highlight a landmark first!")
            return
        idx = int(self._parameterNode.GetParameter("LandmarkWidgetHilightIdx"))
        msg = self._commandsData[s] + "_" + str(idx).zfill(2)
        try:
            self._connections.utilSendCommand(msg)
        except:
            return
        print(msg)

    def processPushToolPosePlan(self, inputMarkupsNode):
        """
        Push botton callback function. Plan the pose of the contact point.
        """

        if not inputMarkupsNode:
            slicer.util.errorDisplay("Input markup is invalid!")
            raise ValueError("Input markup is invalid!")

        if (
            inputMarkupsNode.GetNumberOfFiducials() != 4
            and inputMarkupsNode.GetNumberOfFiducials() != 3
            and inputMarkupsNode.GetNumberOfFiducials() != 2
        ):
            slicer.util.errorDisplay("Input number of landmarks are not 2, 3 or 4!")
            raise ValueError("Input number of landmarks are not 2, 3 or 4!")

        # Get the position and orientation of the planned tool pose on skin or cortex
        p, mat = self.processToolPosePlanByNumOfPoints(inputMarkupsNode)
        drawAPlane(
            mat,
            p,
            self._configPath,
            "PlaneOnMeshIndicator",
            "PlaneOnMeshTransform",
            self._parameterNode,
        )
        self.processToolPosePlanMeshCheck(p, mat)

    def processToolPosePlanMeshCheck(self, p, mat):
        # If planned on skin, then skin search; if planned on cortex, then project on skin
        if self._parameterNode.GetParameter("PlanOnBrain") == "true":
            # 1. Cortex option
            self.processToolPoseParameterNodeSet("TargetPoseTransformCortex", p, mat)
            # 2. Skin option (projected using cortex rot)
            pSkin, matSkin = self.processSearchForSkinProjection(p, mat)
            # print(pSkin, matSkin)
            self.processToolPoseParameterNodeSet(
                "TargetPoseTransformSkin", pSkin, matSkin
            )
            drawAPlane(
                matSkin,
                pSkin,
                self._configPath,
                "PlaneOnMeshSkinIndicator",
                "PlaneOnMeshSkinTransform",
                self._parameterNode,
            )
            # 3. Skin option (Closest. project using the closest on skin)
            pSkinClosest, matSkinClosest = self.processSearchForSkinClosestProjection(p)
            # print(pSkinClosest, matSkinClosest)
            self.processToolPoseParameterNodeSet(
                "TargetPoseTransformSkinClosest", pSkinClosest, matSkinClosest
            )
            drawAPlane(
                matSkinClosest,
                pSkinClosest,
                self._configPath,
                "PlaneOnMeshSkinClosestIndicator",
                "PlaneOnMeshSkinClosestTransform",
                self._parameterNode,
            )

            # Considering the shape mismatch of the skin and cortex (brain), use
            # different ways of orientation calculation
            # 1. Depend only on cortex: the orientation is the cortex shape
            # 2. Depend only on skin: the orientation is the skin shape, at the point
            #   projected from the previously planned point
            # 3. Depend on skin: the orientation is the skin shape, at the closest point on skin
            # 4. Depend on a weighted combination
            # Note, if the pose was planned on skin, then option 2 is the only valid option
            # print(self._parameterNode.GetParameter("ToolRotOption"))
            if self._parameterNode.GetParameter("ToolRotOption") == "cortex":
                p = pSkin
            elif self._parameterNode.GetParameter("ToolRotOption") == "combined":
                slicer.util.errorDisplay("Not implemented yet!")
                return
            elif self._parameterNode.GetParameter("ToolRotOption") == "skin":
                p = pSkin
                mat = matSkin
            else:  # Default is the skinclosest
                p = pSkinClosest
                mat = matSkinClosest

        self.processToolPoseParameterNodeSet("TargetPoseTransform", p, mat)
        self.processToolPosePlanVisualization()
        self.processToolPosePlanSend(p, mat)

    def processToolPosePlanMeshReCheck(self):
        if self._parameterNode.GetParameter("PlanOnBrain") == "true":
            targetPoseTransform = self._parameterNode.GetNodeReference(
                "TargetPoseTransformCortex"
            ).GetMatrixTransformToParent()
            p, mat = getRotAndPFromMatrix(targetPoseTransform)
            targetPoseTransform = self._parameterNode.GetNodeReference(
                "TargetPoseTransformSkin"
            ).GetMatrixTransformToParent()
            pSkin, matSkin = getRotAndPFromMatrix(targetPoseTransform)
            targetPoseTransform = self._parameterNode.GetNodeReference(
                "TargetPoseTransformSkinClosest"
            ).GetMatrixTransformToParent()
            pSkinClosest, matSkinClosest = getRotAndPFromMatrix(targetPoseTransform)
            if self._parameterNode.GetParameter("ToolRotOption") == "cortex":
                p = pSkin
            elif self._parameterNode.GetParameter("ToolRotOption") == "combined":
                slicer.util.errorDisplay("Not implemented yet!")
                return
            elif self._parameterNode.GetParameter("ToolRotOption") == "skin":
                p = pSkin
                mat = matSkin
            else:  # Default is the skinclosest
                p = pSkinClosest
                mat = matSkinClosest
            self.processToolPoseParameterNodeSet("TargetPoseTransform", p, mat)
            self.processToolPosePlanVisualization()
            self.processToolPosePlanSend(p, mat)

    def processToolPoseParameterNodeSet(self, nodename, p, mat):

        if not self._parameterNode.GetNodeReference(nodename):
            transformNode = slicer.vtkMRMLTransformNode()
            transformNodeSingleton = slicer.vtkMRMLTransformNode()
            slicer.mrmlScene.AddNode(transformNode)
            slicer.mrmlScene.AddNode(transformNodeSingleton)
            transformNodeSingleton.SetSingletonTag("MedImgPlan." + nodename)
            self._parameterNode.SetNodeReferenceID(nodename, transformNode.GetID())
            self._parameterNode.SetNodeReferenceID(
                nodename + "Singleton", transformNodeSingleton.GetID()
            )

        transformMatrix = vtk.vtkMatrix4x4()
        transformMatrixSingleton = vtk.vtkMatrix4x4()
        setTransform(mat, p, transformMatrix)
        setTransform(mat, p, transformMatrixSingleton)
        targetPoseTransform = self._parameterNode.GetNodeReference(nodename)
        targetPoseTransformSingleton = self._parameterNode.GetNodeReference(
            nodename + "Singleton"
        )
        targetPoseTransform.SetMatrixTransformToParent(transformMatrix)
        targetPoseTransformSingleton.SetMatrixTransformToParent(
            transformMatrixSingleton
        )

    def processPushToolPosePlanRand(self):
        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            slicer.util.errorDisplay("Please plan tool pose first!")
            return
        targetPoseTransform = self._parameterNode.GetNodeReference(
            "TargetPoseTransform"
        ).GetMatrixTransformToParent()
        temp = vtk.vtkMatrix4x4()
        temp.DeepCopy(targetPoseTransform)

        tempOffset = vtk.vtkMatrix4x4()
        pos_range = 15.0
        tempOffset.SetElement(0, 3, random.uniform(-pos_range, pos_range))
        tempOffset.SetElement(1, 3, random.uniform(-pos_range, pos_range))
        tempOffset.SetElement(2, 3, random.uniform(-pos_range, pos_range))

        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        tempOffset = vtk.vtkMatrix4x4()
        ang_range = 15.0 / 180.0 * math.pi
        setRotation(rotx(random.uniform(-ang_range, ang_range)), tempOffset)
        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
        setRotation(roty(random.uniform(-ang_range, ang_range)), tempOffset)
        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
        setRotation(rotz(random.uniform(-ang_range, ang_range)), tempOffset)
        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        p, mat = getRotAndPFromMatrix(temp)
        self.processToolPoseParameterNodeSet("TargetPoseTransform", p, mat)
        self.processToolPosePlanVisualization()
        self.processToolPosePlanSend(p, mat)

    def processToolPosePlanByNumOfPoints(self, inputMarkupsNode):

        a, b, c, p = [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]

        if inputMarkupsNode.GetNumberOfFiducials() == 4:

            inputMarkupsNode.GetNthFiducialPosition(1, a)
            inputMarkupsNode.GetNthFiducialPosition(2, b)
            inputMarkupsNode.GetNthFiducialPosition(3, c)
            inputMarkupsNode.GetNthFiducialPosition(0, p)
            mat = utilPosePlan(a, b, c, p)
            self._override_y = c

        if inputMarkupsNode.GetNumberOfFiducials() == 3:

            inputMarkupsNode.GetNthFiducialPosition(0, a)
            inputMarkupsNode.GetNthFiducialPosition(1, b)
            inputMarkupsNode.GetNthFiducialPosition(2, c)
            p[0] = (a[0] + b[0] + c[0]) / 3.0
            p[1] = (a[1] + b[1] + c[1]) / 3.0
            p[2] = (a[2] + b[2] + c[2]) / 3.0
            mat = utilPosePlan(a, b, c, p)
            self._override_y = c

        if inputMarkupsNode.GetNumberOfFiducials() == 2:

            override_y = [0, 0, 0]
            inputMarkupsNode.GetNthFiducialPosition(0, p)
            inputMarkupsNode.GetNthFiducialPosition(1, override_y)

            if self._parameterNode.GetParameter("PlanOnBrain") == "true":
                inModel = self._parameterNode.GetNodeReference("InputMeshBrain")
                self._parameterNode.SetNodeReferenceID(
                    "BrainMeshOffsetTransform", inModel.GetParentTransformNode().GetID()
                )
                transformFilter = vtk.vtkTransformPolyDataFilter()
                transformFilterTransform = vtk.vtkTransform()
                transformFilterTransform.SetMatrix(
                    self._parameterNode.GetNodeReference(
                        "BrainMeshOffsetTransform"
                    ).GetMatrixTransformToParent()
                )
                transformFilter.SetTransform(transformFilterTransform)
                transformFilter.SetInputData(inModel.GetPolyData())
                transformFilter.Update()
                inModel = transformFilter.GetOutput()

            if self._parameterNode.GetParameter("PlanOnBrain") == "false":
                inModel = self._parameterNode.GetNodeReference("InputMeshSkin")
                inModel = inModel.GetPolyData()
            if not inModel:
                slicer.util.errorDisplay("Please select a image model first!")
                return

            cellLocator1 = vtk.vtkCellLocator()
            cellLocator1.SetDataSet(inModel)
            cellLocator1.BuildLocator()
            closestPoint = [0.0, 0.0, 0.0]
            cellObj = vtk.vtkGenericCell()
            cellId, subId, dist2 = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
            cellLocator1.FindClosestPoint(
                p, closestPoint, cellObj, cellId, subId, dist2
            )

            cellObj.GetPoints().GetPoint(0, a)
            cellObj.GetPoints().GetPoint(1, b)
            cellObj.GetPoints().GetPoint(2, c)

            mat = utilPosePlan(a, b, c, p, override_y)

            self._override_y = override_y

        return p, mat

    def processSearchForSkinProjection(self, pcortex, matcortex):
        """
        Find the projection pose (pos & rot) on the skin. The rot will be
        the tangential plane on theskin.
        """
        inModel = self._parameterNode.GetNodeReference("InputMeshSkin")

        # Construct cell locator
        cellLocator = vtk.vtkCellLocator()
        cellLocator.SetDataSet(inModel.GetPolyData())
        cellLocator.BuildLocator()

        # Construct a ray from cortex target point, along the perpendicular direction of cortex
        # at the cortex target point.
        ray_point, ray_length = [0.0, 0.0, 0.0], 10000.0
        ray_point[0], ray_point[1], ray_point[2] = (
            pcortex[0] + ray_length * matcortex[0][2],
            pcortex[1] + ray_length * matcortex[1][2],
            pcortex[2] + ray_length * matcortex[2][2],
        )

        # Init some needed parameters.
        cl_pIntSect, cl_pcoords = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        cl_t, cl_sub_id = vtk.mutable(0), vtk.mutable(0)
        a, b, c = [0, 0, 0], [0, 0, 0], [0, 0, 0]
        cellObj = vtk.vtkGenericCell()
        cellId, subId, dist2 = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
        closestPoint = [0.0, 0.0, 0.0]

        # Search for the projected point on the skin.
        cellLocator.IntersectWithLine(
            pcortex, ray_point, 1e-6, cl_t, cl_pIntSect, cl_pcoords, cl_sub_id
        )
        pSkin = [cl_pIntSect[0], cl_pIntSect[1], cl_pIntSect[2]]

        # Search for the tangential plane on the skin
        cellLocator.FindClosestPoint(pSkin, closestPoint, cellObj, cellId, subId, dist2)
        cellObj.GetPoints().GetPoint(0, a)
        cellObj.GetPoints().GetPoint(1, b)
        cellObj.GetPoints().GetPoint(2, c)
        matSkin = utilPosePlan(a, b, c, pSkin, self._override_y)

        return pSkin, matSkin

    def processSearchForSkinClosestProjection(self, pcortex):
        """
        Find the closest point on the skin. The rot will be
        the tangential plane on the skin.
        """
        inModel = self._parameterNode.GetNodeReference("InputMeshSkin")

        # Construct cell locator
        cellLocator = vtk.vtkCellLocator()
        cellLocator.SetDataSet(inModel.GetPolyData())
        cellLocator.BuildLocator()

        # Init some needed parameters.
        a, b, c = [0, 0, 0], [0, 0, 0], [0, 0, 0]
        cellObj = vtk.vtkGenericCell()
        cellId, subId, dist2 = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
        closestPoint = [0.0, 0.0, 0.0]

        # Search for the tangential plane on the skin
        cellLocator.FindClosestPoint(
            pcortex, closestPoint, cellObj, cellId, subId, dist2
        )
        cellObj.GetPoints().GetPoint(0, a)
        cellObj.GetPoints().GetPoint(1, b)
        cellObj.GetPoints().GetPoint(2, c)
        matSkinClosest = utilPosePlan(a, b, c, closestPoint, self._override_y)

        return closestPoint, matSkinClosest

    def processToolPosePlanVisualizationInit(self):
        if not self._parameterNode.GetNodeReference("TargetPoseIndicator"):
            with open(self._configPath + "Config.json") as f:
                configData = json.load(f)
            inputModel = slicer.util.loadModel(
                self._configPath + configData["POSE_INDICATOR_MODEL"]
            )
            self._parameterNode.SetNodeReferenceID(
                "TargetPoseIndicator", inputModel.GetID()
            )
            inputModel.GetDisplayNode().SetColor(0, 1, 0)
        if not self._parameterNode.GetNodeReference("TargetPoseIndicatingLine"):
            lineNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsLineNode", "TargetPoseIndicatingLine"
            )
            self._parameterNode.SetNodeReferenceID(
                "TargetPoseIndicatingLine", lineNode.GetID()
            )

    def processToolPosePlanVisualization(self):
        self.processToolPosePlanVisualizationInit()
        targetPoseIndicator = self._parameterNode.GetNodeReference(
            "TargetPoseIndicator"
        )
        targetPoseIndicator.SetAndObserveTransformNodeID(
            self._parameterNode.GetNodeReference("TargetPoseTransform").GetID()
        )
        lineNode = self._parameterNode.GetNodeReference("TargetPoseIndicatingLine")
        transf = self._parameterNode.GetNodeReference(
            "TargetPoseTransform"
        ).GetMatrixTransformToParent()
        if lineNode.GetNumberOfControlPoints() == 0:
            lineNode.AddControlPoint(0, 0, 0)
            lineNode.AddControlPoint(0, 0, 0)
        lineNode.SetNthControlPointPosition(
            0, transf.GetElement(0, 3), transf.GetElement(1, 3), transf.GetElement(2, 3)
        )
        lineNode.SetNthControlPointPosition(
            1,
            transf.GetElement(0, 3) - transf.GetElement(0, 2) * 50,
            transf.GetElement(1, 3) - transf.GetElement(1, 2) * 50,
            transf.GetElement(2, 3) - transf.GetElement(2, 2) * 50,
        )
        # lineNode.GetDisplayNode().SetSelectedColor(1,0,0)
        lineNode.GetDisplayNode().SetTextScale(0)
        slicer.app.processEvents()

    def processToolPosePlanSend(self, p, mat):
        quat = mat2quat(mat)
        msg = (
            self._commandsData["TARGET_POSE_ORIENTATION"]
            + "_"
            + utilNumStrFormat(quat[0], 15, 17)
            + "_"
            + utilNumStrFormat(quat[1], 15, 17)
            + "_"
            + utilNumStrFormat(quat[2], 15, 17)
            + "_"
            + utilNumStrFormat(quat[3], 15, 17)
        )
        self._connections.utilSendCommand(msg)
        msg = (
            self._commandsData["TARGET_POSE_TRANSLATION"]
            + "_"
            + utilNumStrFormat(p[0] / 1000, 15, 17)
            + "_"
            + utilNumStrFormat(p[1] / 1000, 15, 17)
            + "_"
            + utilNumStrFormat(p[2] / 1000, 15, 17)
        )
        self._connections.utilSendCommand(msg)

    def utilSendLandmarks(self, curIdx):
        """
        Utility function to recurrantly send landmarks (landmarks on medical image)
        """
        inputMarkupsNode = self._parameterNode.GetNodeReference("LandmarksMarkups")
        numOfFid = inputMarkupsNode.GetNumberOfFiducials()

        if curIdx == numOfFid:
            msg = self._commandsData["LANDMARK_LAST_RECEIVED"]
        elif curIdx != -1:
            ras = [0, 0, 0]
            inputMarkupsNode.GetNthFiducialPosition(curIdx, ras)
            # curIdx is -1, send the current landmark
            # Send in SI units (meter/second/...)
            msg = (
                self._commandsData["LANDMARK_CURRENT_ON_IMG"]
                + "_"
                + str(curIdx).zfill(2)
                + "_"
                + utilNumStrFormat(ras[0] / 1000, 15, 17)
                + "_"
                + utilNumStrFormat(ras[1] / 1000, 15, 17)
                + "_"
                + utilNumStrFormat(ras[2] / 1000, 15, 17)
            )
        else:
            # curIdx is -1, send the number of landmarks
            msg = (
                self._commandsData["LANDMARK_NUM_OF_ON_IMG"]
                + "_"
                + str(numOfFid).zfill(2)
            )

        print(msg)

        self._connections.utilSendCommand(msg)

        if curIdx <= numOfFid - 1:
            curIdx = curIdx + 1
            self.utilSendLandmarks(curIdx)

    def processManualAdjustTool(self, arr):
        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            slicer.util.errorDisplay("Please plan tool pose first!")
            return

        targetPoseTransform = self._parameterNode.GetNodeReference(
            "TargetPoseTransform"
        ).GetMatrixTransformToParent()
        temp = vtk.vtkMatrix4x4()
        temp.DeepCopy(targetPoseTransform)

        tempOffset = vtk.vtkMatrix4x4()
        tempOffset.SetElement(0, 3, arr[0])
        tempOffset.SetElement(1, 3, arr[1])
        tempOffset.SetElement(2, 3, arr[2])

        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        tempOffset = vtk.vtkMatrix4x4()
        if arr[3]:
            setRotation(rotx(arr[3]), tempOffset)
        if arr[4]:
            setRotation(roty(arr[4]), tempOffset)
        if arr[5]:
            setRotation(rotz(arr[5]), tempOffset)

        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        p, mat = getRotAndPFromMatrix(temp)
        self.processToolPoseParameterNodeSet("TargetPoseTransform", p, mat)
        self.processToolPosePlanVisualization()
        self.processToolPosePlanSend(p, mat)

    def processManualAdjustReg(self, arr, pathICPPoints):

        ### This method hasn't been completed.
        ### Need:
        ### 1. Send to ROS after finish
        ### 2. Validate error each time it is done

        # check if registration result exists
        if not self._parameterNode.GetNodeReference("TransformICPReg"):
            slicer.util.errorDisplay("Please show ICP results first!")
            return

        # get the original registration result
        targetPoseTransform = self._parameterNode.GetNodeReference(
            "TargetPoseTransform"
        ).GetMatrixTransformToParent()

        # initialize an offset matrix
        temp = vtk.vtkMatrix4x4()
        temp.DeepCopy(targetPoseTransform)

        # apply offset - translation
        tempOffset = vtk.vtkMatrix4x4()
        tempOffset.SetElement(0, 3, arr[0])
        tempOffset.SetElement(1, 3, arr[1])
        tempOffset.SetElement(2, 3, arr[2])
        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        # apply offset - rotation
        tempOffset = vtk.vtkMatrix4x4()
        if arr[3]:
            setRotation(rotx(arr[3]), tempOffset)
        if arr[4]:
            setRotation(roty(arr[4]), tempOffset)
        if arr[5]:
            setRotation(rotz(arr[5]), tempOffset)
        vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)

        p, mat = getRotAndPFromMatrix(temp)

        # Update transformation parameter
        self._parameterNode.GetNodeReference(
            "TransformICPReg"
        ).SetMatrixTransformToParent(temp)

        # load digitized points
        with open(pathICPPoints, "r") as stream:
            try:
                dig_dict = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                return
        dig = []
        for k in dig_dict.keys():
            # convert ROS m unit to mm
            dig.extend([float(i) * 1000.0 for i in dig_dict[k].strip().split(",")[:-1]])
        dig_ = numpy.array(dig).reshape((-1, 3)).transpose()

        # apply new position of the points

        p = numpy.array(p).reshape((3, 1))
        mat = numpy.array(mat)
        res = numpy.matmul(mat, dig_) + p

        # Method 1: change position point by point. Very slow
        # markupsNode = self._parameterNode.GetNodeReference("AlignedICPPointClouds")
        # for idx, i in enumerate(res.transpose()):
        #     markupsNode.SetNthControlPointPosition(idx, i[0], i[1], i[2])

        # Method 2: Remove old and visualize again
        if self._parameterNode.GetNodeReference("AlignedICPPointClouds"):
            markupsNode = self._parameterNode.GetNodeReference("AlignedICPPointClouds")
            slicer.mrmlScene.RemoveNode(markupsNode)
        markupsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "AlignedICP"
        )
        self._parameterNode.SetNodeReferenceID(
            "AlignedICPPointClouds", markupsNode.GetID()
        )
        slicer.modules.markups.logic().SetActiveList(markupsNode)
        markupsNode.GetDisplayNode().SetSelectedColor(0, 1, 0)
        markupsNode.GetDisplayNode().SetTextScale(0)

        for i in res.transpose():
            slicer.modules.markups.logic().AddControlPoint(i[0], i[1], i[2])

        # Disable control point placement
        slicer.mrmlScene.GetNodeByID(
            "vtkMRMLInteractionNodeSingleton"
        ).SetPlaceModePersistence(0)

        slicer.util.infoDisplay("Alignment change complete")

    def processGenerateGridIncrementDir(self, n):
        # Output the direction arr of a squre spiral pattern
        # n > 1
        arr, finished_level = [], 0
        for i in range(n):
            if (i + 1) == 1:
                arr.append(1)
                finished_level = 1
            else:
                if (i + 1) - (2 * (finished_level + 1) - 1) ** 2 == 0:
                    finished_level += 1
                    arr.append(1)
                elif (i + 1) - (2 * finished_level - 1) ** 2 == 1:
                    arr.append(2)
                elif (i + 1) - (2 * finished_level - 1) ** 2 == 2 * (
                    finished_level + 1
                ) - 2:
                    arr.append(3)
                elif (i + 1) - (2 * finished_level - 1) ** 2 == 4 * (
                    finished_level + 1
                ) - 4:
                    arr.append(4)
                elif (i + 1) - (2 * finished_level - 1) ** 2 == 6 * (
                    finished_level + 1
                ) - 6:
                    arr.append(1)
                else:
                    arr.append(arr[-1])
        return arr

    def processGenerateGridCoordinateArr(self, numOfGrid):

        dist = float(self._parameterNode.GetParameter("GridDistanceApart"))
        arr = self.processGenerateGridIncrementDir(numOfGrid)

        if self._parameterNode.GetParameter("PlanOnBrain") == "true":
            targetPoseTransform = self._parameterNode.GetNodeReference(
                "TargetPoseTransformCortex"
            ).GetMatrixTransformToParent()
        else:
            targetPoseTransform = self._parameterNode.GetNodeReference(
                "TargetPoseTransform"
            ).GetMatrixTransformToParent()

        temp1, temp = vtk.vtkMatrix4x4(), vtk.vtkMatrix4x4()
        temp1.DeepCopy(targetPoseTransform)
        temp.DeepCopy(targetPoseTransform)

        coor = [temp1]
        arr.pop()

        for i in arr:
            temp2 = vtk.vtkMatrix4x4()
            tempOffset = vtk.vtkMatrix4x4()
            if i == 1:
                tempOffset.SetElement(0, 3, dist)
                vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
                temp2.DeepCopy(temp)
                coor.append(temp2)
            if i == 2:
                tempOffset.SetElement(1, 3, dist)
                vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
                temp2.DeepCopy(temp)
                coor.append(temp2)
            if i == 3:
                tempOffset.SetElement(0, 3, -dist)
                vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
                temp2.DeepCopy(temp)
                coor.append(temp2)
            if i == 4:
                tempOffset.SetElement(1, 3, -dist)
                vtk.vtkMatrix4x4.Multiply4x4(temp, tempOffset, temp)
                temp2.DeepCopy(temp)
                coor.append(temp2)
        return coor

    def processClearPrevGridPlan(self):
        if self._parameterNode.GetParameter("GridPlanIndicatorNumPrev"):
            prevnum = int(
                float(self._parameterNode.GetParameter("GridPlanIndicatorNumPrev"))
            )
            curnum = int(float(self._parameterNode.GetParameter("GridPlanNum")))
            for i in range(prevnum):
                if i >= curnum:
                    slicer.mrmlScene.RemoveNode(
                        self._parameterNode.GetNodeReference(
                            "GridPlanTransformNum" + str(i)
                        )
                    )
                    slicer.mrmlScene.RemoveNode(
                        self._parameterNode.GetNodeReference(
                            "GridPlanIndicatorNum" + str(i)
                        )
                    )

    def processVisualizeAndLogPlanGrid(self, coor):

        self.processClearPrevGridPlan()
        with open(self._configPath + "Config.json") as f:
            configData = json.load(f)
        idx = -1

        if self._parameterNode.GetParameter("PlanOnBrain") == "true":
            inModel = self._parameterNode.GetNodeReference("InputMeshBrain")
            self._parameterNode.SetNodeReferenceID(
                "BrainMeshOffsetTransform", inModel.GetParentTransformNode().GetID()
            )
            transformFilter = vtk.vtkTransformPolyDataFilter()
            transformFilterTransform = vtk.vtkTransform()
            transformFilterTransform.SetMatrix(
                self._parameterNode.GetNodeReference(
                    "BrainMeshOffsetTransform"
                ).GetMatrixTransformToParent()
            )
            transformFilter.SetTransform(transformFilterTransform)
            transformFilter.SetInputData(inModel.GetPolyData())
            transformFilter.Update()
            inModel = transformFilter.GetOutput()
        if self._parameterNode.GetParameter("PlanOnBrain") == "false":
            inModel = self._parameterNode.GetNodeReference("InputMeshSkin")
            inModel = inModel.GetPolyData()
        if not inModel:
            slicer.util.errorDisplay("Please select a image model first!")
            return

        for i in coor:
            idx += 1

            p, mat = getRotAndPFromMatrix(i)
            cellLocator2 = vtk.vtkCellLocator()
            cellLocator2.SetDataSet(inModel)
            cellLocator2.BuildLocator()

            ray_length = 0.0
            cl_pIntSect = [float("nan"), float("nan"), float("nan")]
            while math.isnan(sum(cl_pIntSect)) and ray_length < 1000:
                ray_point1, ray_point2 = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
                ray_length += 5.0

                ray_point1[0], ray_point1[1], ray_point1[2] = (
                    p[0] + ray_length * mat[0][2],
                    p[1] + ray_length * mat[1][2],
                    p[2] + ray_length * mat[2][2],
                )
                ray_point2[0], ray_point2[1], ray_point2[2] = (
                    p[0] - ray_length * mat[0][2],
                    p[1] - ray_length * mat[1][2],
                    p[2] - ray_length * mat[2][2],
                )

                cl_pIntSect, cl_pcoords = [float("nan"), float("nan"), float("nan")], [
                    0.0,
                    0.0,
                    0.0,
                ]
                cellObj, cellId, cl_t, cl_sub_id = (
                    vtk.vtkGenericCell(),
                    vtk.mutable(0),
                    vtk.mutable(0),
                    vtk.mutable(0),
                )
                cellLocator2.IntersectWithLine(
                    ray_point1,
                    ray_point2,
                    1e-6,
                    cl_t,
                    cl_pIntSect,
                    cl_pcoords,
                    cl_sub_id,
                    cellId,
                    cellObj,
                )

            p[0], p[1], p[2] = cl_pIntSect[0], cl_pIntSect[1], cl_pIntSect[2]

            a, b, c = [0, 0, 0], [0, 0, 0], [0, 0, 0]
            cellObj.GetPoints().GetPoint(0, a)
            cellObj.GetPoints().GetPoint(1, b)
            cellObj.GetPoints().GetPoint(2, c)

            mat = utilPosePlan(a, b, c, p, self._override_y)

            setTranslation(p, i)
            setRotation(mat, i)

            initModelAndTransform(
                self._parameterNode,
                "GridPlanTransformNum" + str(idx),
                i,
                "GridPlanIndicatorNum" + str(idx),
                self._configPath + configData["POSE_INDICATOR_NOTAIL_MODEL"],
            )
            self._parameterNode.GetNodeReference(
                "GridPlanIndicatorNum" + str(idx)
            ).GetDisplayNode().SetColor(0, 0, 1)
            if idx == 0:
                self._parameterNode.GetNodeReference(
                    "GridPlanIndicatorNum" + str(idx)
                ).GetDisplayNode().SetColor(0, 1, 1)
        self._parameterNode.SetParameter(
            "GridPlanIndicatorNumPrev", self._parameterNode.GetParameter("GridPlanNum")
        )
        self._parameterNode.SetParameter("GridPlanCurrentAt", "0")

    def processPlanGrid(self):

        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            slicer.util.errorDisplay("Please plan tool pose first!")
            raise ValueError("Please plan tool pose first!")

        # if (self._parameterNode.GetParameter("PlanGridOnPerspPlane") == "true") \
        #     and (self._parameterNode.GetParameter("PlanGridOnAnatomySurf") == "true"):
        #         slicer.util.errorDisplay("Please only check one method!")
        #         raise ValueError("Please only check one method!")

        numOfGrid = int(float(self._parameterNode.GetParameter("GridPlanNum")))
        if numOfGrid > 1:

            if self._parameterNode.GetParameter("PlanGridOnPerspPlane") == "true":
                coor = self.processGenerateGridCoordinateArr(numOfGrid)
                self.processVisualizeAndLogPlanGrid(coor)

            # if (self._parameterNode.GetParameter("PlanGridOnAnatomySurf") == "true"):

    def processGridSetNext(self):

        numOfGrid = int(float(self._parameterNode.GetParameter("GridPlanNum")))
        if numOfGrid > 1:
            cur = int(float(self._parameterNode.GetParameter("GridPlanCurrentAt")))
            if cur == numOfGrid - 1:
                cur = 0
            else:
                cur += 1
            self._parameterNode.SetParameter("GridPlanCurrentAt", str(cur))
            p, mat = getRotAndPFromMatrix(
                self._parameterNode.GetNodeReference(
                    "GridPlanTransformNum" + str(cur)
                ).GetMatrixTransformToParent()
            )
            drawAPlane(
                mat,
                p,
                self._configPath,
                "PlaneOnMeshIndicator",
                "PlaneOnMeshTransform",
                self._parameterNode,
            )
            self.processToolPosePlanMeshCheck(p, mat)
            # following 3 lines might be redundant. check!
            self.processToolPosePlanVisualization()
            self.processToolPosePlanSend(p, mat)
            self.processToolPosePlanMeshReCheck()

    def processRetrieveToolPose(self, path):
        if path.endswith(".yaml"):
            with open(path, "r") as stream:
                try:
                    file = yaml.safe_load(stream)
                    mat = [
                        file["ROTATION"]["x"],
                        file["ROTATION"]["y"],
                        file["ROTATION"]["z"],
                        file["ROTATION"]["w"],
                    ]
                    mat = quat2mat(mat)
                    p = [
                        file["TRANSLATION"]["x"] * 1000.0,
                        file["TRANSLATION"]["y"] * 1000.0,
                        file["TRANSLATION"]["z"] * 1000.0,
                    ]
                    drawAPlane(
                        mat,
                        p,
                        self._configPath,
                        "PlaneOnMeshIndicator",
                        "PlaneOnMeshTransform",
                        self._parameterNode,
                    )
                    self.processToolPoseParameterNodeSet("TargetPoseTransform", p, mat)
                    self.processToolPosePlanVisualization()
                    self.processToolPosePlanSend(p, mat)
                except yaml.YAMLError as exc:
                    print(exc)
                    return
        else:
            slicer.util.errorDisplay("File invalid!")

    def processHeatMapOnBrain(self, mep, targetPoseTransform, inmodel):

        self._parameterNode.SetNodeReferenceID(
            "BrainMeshOffsetTransform", inmodel.GetParentTransformNode().GetID()
        )
        transformFilter = vtk.vtkTransformPolyDataFilter()
        transformFilterTransform = vtk.vtkTransform()
        transformFilterTransform.SetMatrix(
            self._parameterNode.GetNodeReference(
                "BrainMeshOffsetTransform"
            ).GetMatrixTransformToParent()
        )
        transformFilter.SetTransform(transformFilterTransform)
        transformFilter.SetInputData(inmodel.GetPolyData())
        transformFilter.Update()
        poly_data = transformFilter.GetOutput()

        # Create a OBB tree
        obb_tree = vtk.vtkOBBTree()
        obb_tree.SetDataSet(poly_data)
        obb_tree.BuildLocator()

        # Define the ray from the target pose with a length of 50 mm
        ray_length = 50.0
        ray_point1, ray_point2 = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        ray_point1[0], ray_point1[1], ray_point1[2] = (
            targetPoseTransform.GetElement(0, 3),
            targetPoseTransform.GetElement(1, 3),
            targetPoseTransform.GetElement(2, 3),
        )  # start point
        ray_point2[0], ray_point2[1], ray_point2[2] = (
            targetPoseTransform.GetElement(0, 3)
            - ray_length * targetPoseTransform.GetElement(0, 2),
            targetPoseTransform.GetElement(1, 3)
            - ray_length * targetPoseTransform.GetElement(1, 2),
            targetPoseTransform.GetElement(2, 3)
            - ray_length * targetPoseTransform.GetElement(2, 2),
        )  # end point

        # Find the intersection point on the mesh to the ray
        intersection_points = vtk.vtkPoints()
        code = obb_tree.IntersectWithLine(
            ray_point1, ray_point2, intersection_points, None
        )
        if code == 0:
            slicer.util.errorDisplay("No intersection found!")
            return
        else:
            closest_point = intersection_points.GetPoint(
                0
            )  # Pick the intersection point with minimum distance

        # insert this closest point to the parameter node named "TargetPointOnCortex"
        # this node a vtkPoints node
        if not self._parameterNode.GetNodeReference("TargetPointOnCortex"):
            targetPointOnCortex = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode", "TargetPointOnCortex"
            )
            self._parameterNode.SetNodeReferenceID(
                "TargetPointOnCortex", targetPointOnCortex.GetID()
            )
        else:
            targetPointOnCortex = self._parameterNode.GetNodeReference("TargetPointOnCortex")

        targetPointOnCortex.InsertControlPoint(0, closest_point)
        targetPointOnCortex.SetNthControlPointVisibility(0, False)

        POINT_COUNT = poly_data.GetNumberOfPoints()
        distances = numpy.zeros(POINT_COUNT)

        for i in range(POINT_COUNT):
            mesh_point = poly_data.GetPoint(i)
            distance = math.sqrt(
                vtk.vtkMath.Distance2BetweenPoints(
                    closest_point,
                    mesh_point,
                )
            )  # distance from target pose to point
            distances[i] = distance

        # print the range of distances
        scalars = computeScalarFromDistance(distances, mep, MAX_MEP=1.0)
        scalar_values = poly_data.GetPointData().GetScalars()

        now = datetime.datetime.now()
        filename = f"{now.year}.{now.month}.{now.day}.{now.hour}.{now.minute}.{now.second}.json"
        # get the current working directory
        path = os.getcwd()
        with open(os.path.join(path, filename), 'w') as fp:
            fp.write(f"Main coordinates: {intersection_points.GetPoint(0) }  and MEP value: {mep} \n")

        if not scalar_values:
            scalar_values = vtk.vtkDoubleArray()
            scalar_values.SetNumberOfComponents(1)
            scalar_values.SetName("MEPHeatMapScalars")
            scalar_values.SetNumberOfValues(POINT_COUNT)
            for i in range(POINT_COUNT):
                scalar_values.SetValue(i, scalars[i])

        else:
            print("scalar values already exist, adding new values ...")
            for i in range(POINT_COUNT):
                curr_value = scalar_values.GetValue(i)
                scalar_values.SetValue(
                    i, max(curr_value, scalars[i])
                )  # using max value logic
                # but using average is also valid

        # poly_data.GetPointData().SetScalars(scalar_values)
        inmodel.GetPolyData().GetPointData().SetScalars(scalar_values)
        inmodel.GetDisplayNode().SetActiveScalarName("MEPHeatMapScalars")
        inmodel.GetDisplayNode().SetScalarVisibility(True)
        inmodel.GetDisplayNode().AutoScalarRangeOn()
        
        inmodel.GetDisplayNode().AutoScalarRangeOff()
        inmodel.GetDisplayNode().SetScalarRange(0.0, 1.0)
        self.processConfigModelLegend(inmodel)
        slicer.app.processEvents()
        slicer.util.setSliceViewerLayers(background=inmodel)
    
    def processConfigModelLegend(self, inModel, useBuiltInPalette=True):
        # ColorNodeRainbow = slicer.util.getFirstNodeByName("ColdToHotRainbow") # Get the rainbow color node
        if useBuiltInPalette:
            colorNodeCustom = slicer.util.getFirstNodeByName("ColdToHotRainbow")
            # set the color of zero as white
            colorNodeCustom.SetColor(0, 1.0, 1.0, 1.0)
        else:
            colorNodeCustom = slicer.mrmlScene.CreateNodeByClass(
                "vtkMRMLProceduralColorNode"
            )
            colorNodeCustom.UnRegister(None)
            colorNodeCustom.SetName("MEPHeatMapColorNode")
            colorNodeCustom.SetAttribute("Category", "HeatMap")
            colorNodeCustom.SetHideFromEditors(False)
            slicer.mrmlScene.AddNode(colorNodeCustom)

            # Create a lookup table to map scalar values to colors
            
            colorMapCustom = colorNodeCustom.GetColorTransferFunction()
            colorMapCustom.RemoveAllPoints()
            colorMapCustom.AddRGBPoint(0.0, 1.0, 1.0, 1.0)

            # The color range is from yellow to red
            colorMapCustom.AddRGBPoint(1e-6, 1.0, 1.0, 0.0)
            colorMapCustom.AddRGBPoint(1.0, 1.0, 0.0, 0.0)

        inModel.GetDisplayNode().SetAndObserveColorNodeID(colorNodeCustom.GetID())
        colorLegendDisplayNode = (
            slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(inModel)
        )
        colorLegendDisplayNode.SetLabelFormat("%4.3f mV")
        colorLegendDisplayNode.SetTitleText("MEP Responses")

        titleProperties = colorLegendDisplayNode.GetTitleTextProperty()
        titleProperties.SetFontSize(32)
        titleProperties.SetColor(0, 0, 0)
        titleProperties.SetBold(True)
        # titleProperties.SetItalic(True)
        titleProperties.SetShadow(True)
        titleProperties.SetFontFamilyToArial()

        labelProperties = colorLegendDisplayNode.GetLabelTextProperty()
        labelProperties.SetFontSize(16)
        labelProperties.SetColor(0, 0, 0)
        labelProperties.SetBold(True)
        # labelProperties.SetItalic(True)
        labelProperties.SetShadow(True)
        labelProperties.SetFontFamilyToArial()

    def processResetCortex(self, inModel):
        scalar_values = inModel.GetPolyData().GetPointData().GetScalars()
        POINT_COUNT = inModel.GetPolyData().GetNumberOfPoints()
        for i in range(POINT_COUNT):
            scalar_values.SetValue(i, 0.0)

        inModel.GetPolyData().GetPointData().SetScalars(scalar_values)
        inModel.GetDisplayNode().AutoScalarRangeOn()
        inModel.GetDisplayNode().ScalarVisibilityOff()

        # destory the target point on cortex node
        targetPointOnCortex = self._parameterNode.GetNodeReference("TargetPointOnCortex")
        targetPointOnCortex.RemoveAllMarkups()

        slicer.app.processEvents()
        slicer.util.setSliceViewerLayers(background=inModel)

    def processUniformColoring(self, inModel):
        # calculate the tool pose from the given grid
        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            slicer.util.errorDisplay("Please plan tool pose first!")
            raise ValueError("Please plan tool pose first!")

        numOfGrid = int(float(self._parameterNode.GetParameter("GridPlanNum")))
        if numOfGrid > 1:

            if self._parameterNode.GetParameter("PlanGridOnPerspPlane") == "true":
                coor = self.processGenerateGridCoordinateArr(numOfGrid)

        # Obtain the brain model and adjust it by default transformation
        self._parameterNode.SetNodeReferenceID(
            "BrainMeshOffsetTransform", inModel.GetParentTransformNode().GetID()
        )
        transformFilter = vtk.vtkTransformPolyDataFilter()
        transformFilterTransform = vtk.vtkTransform()
        transformFilterTransform.SetMatrix(
            self._parameterNode.GetNodeReference(
                "BrainMeshOffsetTransform"
            ).GetMatrixTransformToParent()
        )
        transformFilter.SetTransform(transformFilterTransform)
        transformFilter.SetInputData(inModel.GetPolyData())
        transformFilter.Update()
        poly_data = transformFilter.GetOutput()

        point_locator = vtk.vtkPointLocator() # Point locator object for finding closest points
        point_locator.SetDataSet(poly_data)
        point_locator.BuildLocator()

        closest_points = []
        indices = []
        targetPointOnCortex = self._parameterNode.GetNodeReference("TargetPointOnCortex")
        for i in range(targetPointOnCortex.GetNumberOfFiducials()):
            ras = [0, 0, 0]
            targetPointOnCortex.GetNthFiducialPosition(i, ras)
            closest_id = point_locator.FindClosestPoint(ras)
            closest_point = poly_data.GetPoint(closest_id)
            closest_points.append(closest_point)
            indices.append(closest_id)

        # get the neighbors of the closest points
        neighbors = {}
        search_radius = 2.5 # [Feature Requested]: A value that can be loaded from the config

        for i in range(len(closest_points)):
            closestIDs = vtk.vtkIdList()
            point_locator.FindPointsWithinRadius(search_radius, closest_points[i], closestIDs)
            neighbors[indices[i]] = [closestIDs.GetId(j) for j in range(closestIDs.GetNumberOfIds())]
        
        grid_neighbor = set()
        for value in neighbors.values():
            grid_neighbor.update(value)
        
        scalar_values = poly_data.GetPointData().GetScalars()
        grid_points_values = [scalar_values.GetValue(i) for i in indices]

        for scalar_id in range(poly_data.GetNumberOfPoints()):
            if scalar_id in grid_neighbor:
                matching_keys = [key for key, value in neighbors.items() if scalar_id in value]
                scalar_values.SetValue(scalar_id,numpy.mean([scalar_values.GetValue(key) for key in matching_keys]))
            else:
                scalar_values.SetValue(scalar_id, 0.0)
        
        for grid_point_id, scalar in zip(indices, grid_points_values):
            scalar_values.SetValue(grid_point_id, scalar)

        inModel.GetPolyData().GetPointData().SetScalars(scalar_values)
        inModel.GetDisplayNode().AutoScalarRangeOn()
        inModel.GetDisplayNode().AutoScalarRangeOff()
        inModel.GetDisplayNode().SetScalarRange(0.0, 1.0)
            
        slicer.app.processEvents()
        slicer.util.setSliceViewerLayers(background=inModel)