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

import slicer, os, json, logging, math, vtk, qt, ctk
from MedImgPlanLib.WidgetMedImgBase import MedImgPlanWidgetBase
from MedImgPlanLib.UtilSlicerFuncs import getRotAndPFromMatrix
from MedImgPlanLib.UtilCalculations import quat2mat


class MedImgPlanWidget(MedImgPlanWidgetBase):

    def __init__(self, parent=None):
        super().__init__(parent)

    def setup(self):
        super().setup()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose
        )
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose
        )

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).

        self.ui.markupsRegistration.connect(
            "markupsNodeChanged()", self.updateParameterNodeFromGUI
        )
        self.ui.markupsToolPosePlan.connect(
            "markupsNodeChanged()", self.updateParameterNodeFromGUI
        )
        self.ui.markupsRegistration.connect(
            "currentMarkupsControlPointSelectionChanged(int)",
            self.onLandmarkWidgetHilightChange,
        )

        self.ui.markupsToolPosePlan.markupsPlaceWidget().setPlaceModePersistency(True)
        self.ui.markupsRegistration.markupsPlaceWidget().setPlaceModePersistency(True)

        self.ui.comboMeshSelectorSkin.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.comboMeshSelectorBrain.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.comboMeshSelectorCoil.connect(
            "currentIndexChanged(int)", self.updateParameterNodeFromGUI
        )
        for name in self.logic._coilModelFiles.keys():
            self.ui.comboMeshSelectorCoil.addItem(name)

        self.ui.checkPlanBrain.connect("toggled(bool)", self.updateParameterNodeFromGUI)

        self.ui.sliderColorThresh.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderManualToolPos.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderManualToolRot.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderManualRegPos.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderManualRegRot.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderGridDistanceApart.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )
        self.ui.sliderGridPlanNum.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI
        )

        self.ui.checkBoxGridAnatomySurf.connect(
            "toggled(bool)", self.updateParameterNodeFromGUI
        )
        self.ui.checkBoxGridPerspPlane.connect(
            "toggled(bool)", self.updateParameterNodeFromGUI
        )

        self.ui.radioButtonToolRotSkin.connect(
            "toggled(bool)", self.onRadioToolRotOptions
        )
        self.ui.radioButtonToolRotCortex.connect(
            "toggled(bool)", self.onRadioToolRotOptions
        )
        self.ui.radioButtonToolRotCombined.connect(
            "toggled(bool)", self.onRadioToolRotOptions
        )
        self.ui.radioButtonToolRotSkinClosest.connect(
            "toggled(bool)", self.onRadioToolRotOptions
        )

        # Buttons

        # Jump to other modules
        self.ui.pushModuleTargetViz.connect("clicked(bool)", self.onPushModuleTargetViz)
        self.ui.pushModuleRobCtrl.connect("clicked(bool)", self.onPushModuleRobCtrl)
        self.ui.pushModuleFreeSurfer.connect(
            "clicked(bool)", self.onPushModuleFreeSurfer
        )
        self.ui.pushModuleSimulation.connect("clicked(bool)", self.onPushModuleSimulation)

        # Registration error estimation
        self.ui.pushStartTRE.connect("clicked(bool)", self.onPushStartTRE)
        self.ui.pushStopTRE.connect("clicked(bool)", self.onPushStopTRE)
        self.ui.pushVisFRE.connect("clicked(bool)", self.onPushVisFRE)

        # Pair-point registration
        self.ui.pushPlanLandmarks.connect("clicked(bool)", self.onPushPlanLandmarks)
        self.ui.pushDigHighlighted.connect("clicked(bool)", self.onPushDigHighlighted)
        self.ui.pushDigitize.connect("clicked(bool)", self.onPushDigitize)
        self.ui.pushDigPrev.connect("clicked(bool)", self.onPushDigPrev)
        self.ui.pushDigPrevAndDigHilight.connect(
            "clicked(bool)", self.onPushDigPrevAndDigHilight
        )
        self.ui.pushRegister.connect("clicked(bool)", self.onPushRegistration)
        self.ui.pushUsePreviousRegistration.connect(
            "clicked(bool)", self.onPushUsePreviousRegistration
        )

        # ICP registration
        self.ui.pushICPDigitize.connect("clicked(bool)", self.onPushICPDigitize)
        self.ui.pushICPClearPrev.connect("clicked(bool)", self.onPushICPClearPrev)
        self.ui.pushICPClearPoints.connect("clicked(bool)", self.onPushICPClearPoints)
        self.ui.pushICPRegister.connect("clicked(bool)", self.onPushICPRegister)
        self.ui.pushShowICPPoints.connect("clicked(bool)", self.onPushShowICPPoints)

        # Manual alignment registrtion
        self.ui.pushBackForwardReg.connect("clicked(bool)", self.onPushBackForwardReg)
        self.ui.pushCloseAwayReg.connect("clicked(bool)", self.onPushCloseAwayReg)
        self.ui.pushLeftRightReg.connect("clicked(bool)", self.onPushLeftRightReg)
        self.ui.pushPitchReg.connect("clicked(bool)", self.onPushPitchReg)
        self.ui.pushRollReg.connect("clicked(bool)", self.onPushRollReg)
        self.ui.pushYawReg.connect("clicked(bool)", self.onPushYawReg)

        # Tool plan
        self.ui.pushToolPosePlan.connect("clicked(bool)", self.onPushToolPosePlan)
        self.ui.pushToolPosePlanRand.connect(
            "clicked(bool)", self.onPushToolPosePlanRand
        )
        self.ui.pushToolPoseExternalStart.connect(
            "clicked(bool)", self.onPushToolPoseExternalStart
        )
        self.ui.pushToolPoseExternalEnd.connect(
            "clicked(bool)", self.onPushToolPoseExternalEnd
        )

        # Tool plan manual adjustment
        self.ui.pushBackForward.connect("clicked(bool)", self.onPushBackForward)
        self.ui.pushCloseAway.connect("clicked(bool)", self.onPushCloseAway)
        self.ui.pushLeftRight.connect("clicked(bool)", self.onPushLeftRight)
        self.ui.pushPitch.connect("clicked(bool)", self.onPushPitch)
        self.ui.pushRoll.connect("clicked(bool)", self.onPushRoll)
        self.ui.pushYaw.connect("clicked(bool)", self.onPushYaw)

        # Grid plan
        self.ui.pushPlanGrid.connect("clicked(bool)", self.onPushPlanGrid)
        self.ui.pushGridSetNext.connect("clicked(bool)", self.onPushGridSetNext)
        self.ui.pushGridClear.connect("clicked(bool)", self.onPushGridClear)

        # MEP Visualization
        self.ui.pushRetrieveToolPose.connect(
            "clicked(bool)", self.onPushRetrieveToolPose
        )
        self.ui.pushOverlayHeatMap.connect("clicked(bool)", self.onPushOverlayHeatMap)
        self.ui.pushResetCortex.connect("clicked(bool)", self.onPushResetCortex)
        self.ui.pushUniformColoring.connect("clicked(bool)", self.onPushUniformColoring)



        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.markupsRegistration.setCurrentNode(
            self._parameterNode.GetNodeReference("LandmarksMarkups")
        )
        self.ui.markupsToolPosePlan.setCurrentNode(
            self._parameterNode.GetNodeReference("ToolPoseMarkups")
        )
        self.ui.comboMeshSelectorSkin.setCurrentNode(
            self._parameterNode.GetNodeReference("InputMeshSkin")
        )
        self.ui.comboMeshSelectorBrain.setCurrentNode(
            self._parameterNode.GetNodeReference("InputMeshBrain")
        )
        coilName = self._parameterNode.GetParameter("CoilModelName")
        if coilName:
            idx = self.ui.comboMeshSelectorCoil.findText(coilName)
            if idx >= 0:
                self.ui.comboMeshSelectorCoil.setCurrentIndex(idx)
        self.ui.sliderColorThresh.value = float(
            self._parameterNode.GetParameter("ColorChangeThresh")
        )
        self.ui.sliderGridDistanceApart.value = float(
            self._parameterNode.GetParameter("GridDistanceApart")
        )
        self.ui.sliderGridPlanNum.value = float(
            self._parameterNode.GetParameter("GridPlanNum")
        )
        self.ui.checkPlanBrain.checked = (
            self._parameterNode.GetParameter("PlanOnBrain") == "true"
        )
        # self.ui.checkBoxGridAnatomySurf.checked = (
        #     self._parameterNode.GetParameter("PlanGridOnAnatomySurf") == "true")
        self.ui.checkBoxGridPerspPlane.checked = (
            self._parameterNode.GetParameter("PlanGridOnPerspPlane") == "true"
        )
        self.ui.radioButtonToolRotSkin.checked = (
            self._parameterNode.GetParameter("ToolRotOption") == "skin"
        )
        self.ui.radioButtonToolRotSkinClosest.checked = (
            self._parameterNode.GetParameter("ToolRotOption") == "skinclosest"
        )
        self.ui.radioButtonToolRotCortex.checked = (
            self._parameterNode.GetParameter("ToolRotOption") == "cortex"
        )
        self.ui.radioButtonToolRotCombined.checked = (
            self._parameterNode.GetParameter("ToolRotOption") == "combined"
        )

        # Update buttons states and tooltips
        if self._parameterNode.GetNodeReference("LandmarksMarkups"):
            self.ui.pushPlanLandmarks.toolTip = "Feed in all the landmarks"
            self.ui.pushPlanLandmarks.enabled = True
            self.ui.pushDigitize.toolTip = "Start digitizing"
            self.ui.pushDigitize.enabled = True
            self.ui.pushDigHighlighted.toolTip = "Digitize a highlighted landmark"
            self.ui.pushDigHighlighted.enabled = True
            self.ui.pushDigPrevAndDigHilight.toolTip = (
                "Use previous digitization, and \n digitize a highlighted landmark"
            )
            self.ui.pushDigPrevAndDigHilight.enabled = True
            self.ui.pushRegister.toolTip = "Register"
            self.ui.pushRegister.enabled = True
        else:
            self.ui.pushPlanLandmarks.toolTip = "Select landmark markups node first"
            self.ui.pushPlanLandmarks.enabled = False
            self.ui.pushDigitize.toolTip = "Select landmark markups node first"
            self.ui.pushDigitize.enabled = False
            self.ui.pushDigHighlighted.toolTip = "Select landmark markups node first"
            self.ui.pushDigHighlighted.enabled = False
            self.ui.pushDigPrevAndDigHilight.toolTip = (
                "Select landmark markups node first"
            )
            self.ui.pushDigPrevAndDigHilight.enabled = False
            self.ui.pushRegister.toolTip = "Select landmark markups node first"
            self.ui.pushRegister.enabled = False

        if self._parameterNode.GetNodeReference("ToolPoseMarkups"):
            self.ui.pushToolPosePlan.toolTip = "Feed in tool pose"
            self.ui.pushToolPosePlan.enabled = True
            self.ui.pushToolPosePlanRand.toolTip = "Feed in tool pose"
            self.ui.pushToolPosePlanRand.enabled = True
        else:
            self.ui.pushToolPosePlan.toolTip = "Select landmark markups node"
            self.ui.pushToolPosePlan.enabled = False
            self.ui.pushToolPosePlanRand.toolTip = "Select landmark markups node"
            self.ui.pushToolPosePlanRand.enabled = False

        if self._parameterNode.GetParameter("PlanOnBrain") == "false":
            self.ui.radioButtonToolRotCombined.enabled = False
            self.ui.radioButtonToolRotCortex.enabled = False
            self.ui.radioButtonToolRotSkinClosest.enabled = False
        else:
            self.ui.radioButtonToolRotCombined.enabled = True
            self.ui.radioButtonToolRotCortex.enabled = True
            self.ui.radioButtonToolRotSkinClosest.enabled = True

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Modify all properties in a single batch
        wasModified = self._parameterNode.StartModify()

        self._parameterNode.SetNodeReferenceID(
            "InputMeshSkin", self.ui.comboMeshSelectorSkin.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputMeshBrain", self.ui.comboMeshSelectorBrain.currentNodeID
        )
        self._parameterNode.SetParameter(
            "CoilModelName", self.ui.comboMeshSelectorCoil.currentText
        )
        self._parameterNode.SetParameter(
            "ColorChangeThresh", str(self.ui.sliderColorThresh.value)
        )
        self._parameterNode.SetParameter(
            "ManualAdjustToolPoseRot", str(self.ui.sliderManualToolRot.value)
        )
        self._parameterNode.SetParameter(
            "ManualAdjustToolPosePos", str(self.ui.sliderManualToolPos.value)
        )
        self._parameterNode.SetParameter(
            "ManualAdjustRegPoseRot", str(self.ui.sliderManualRegRot.value)
        )
        self._parameterNode.SetParameter(
            "ManualAdjustRegPosePos", str(self.ui.sliderManualRegPos.value)
        )
        self._parameterNode.SetParameter(
            "GridDistanceApart", str(self.ui.sliderGridDistanceApart.value)
        )
        self._parameterNode.SetParameter(
            "GridPlanNum", str(self.ui.sliderGridPlanNum.value)
        )
        self._parameterNode.SetParameter(
            "PlanOnBrain", "true" if self.ui.checkPlanBrain.checked else "false"
        )

        # Grid plan pair
        # self._parameterNode.SetParameter(
        #     "PlanGridOnAnatomySurf", "true" if self.ui.checkBoxGridAnatomySurf.checked else "false")
        self._parameterNode.SetParameter(
            "PlanGridOnPerspPlane",
            "true" if self.ui.checkBoxGridPerspPlane.checked else "false",
        )

        # Tool Orientation Options
        if self.ui.radioButtonToolRotSkin.checked:
            self._parameterNode.SetParameter("ToolRotOption", "skin")
        if self._parameterNode.GetParameter("PlanOnBrain") == "true":
            if self.ui.radioButtonToolRotCortex.checked:
                self._parameterNode.SetParameter("ToolRotOption", "cortex")
            if self.ui.radioButtonToolRotCombined.checked:
                self._parameterNode.SetParameter("ToolRotOption", "combined")
            if self.ui.radioButtonToolRotSkinClosest.checked:
                self._parameterNode.SetParameter("ToolRotOption", "skinclosest")
        else:
            self._parameterNode.SetParameter("ToolRotOption", "skin")

        if self.ui.markupsRegistration.currentNode():
            self._parameterNode.SetNodeReferenceID(
                "LandmarksMarkups", self.ui.markupsRegistration.currentNode().GetID()
            )
        else:
            self._parameterNode.SetNodeReferenceID("LandmarksMarkups", None)
        if self.ui.markupsToolPosePlan.currentNode():
            self._parameterNode.SetNodeReferenceID(
                "ToolPoseMarkups", self.ui.markupsToolPosePlan.currentNode().GetID()
            )
        else:
            self._parameterNode.SetNodeReferenceID("ToolPoseMarkups", None)

        self._parameterNode.EndModify(wasModified)

    def onPushModuleRobCtrl(self):
        slicer.util.selectModule("RobotControl")

    def onPushModuleTargetViz(self):
        slicer.util.selectModule("TargetVisualization")

    def onPushModuleFreeSurfer(self):
        slicer.util.selectModule("FreeSurferImporter")

    def onPushModuleSimulation(self):
        slicer.util.selectModule("Simulation")

    def onPushStartTRE(self):
        msg = self.logic._commandsData["START_TRE_CALCULATION_START"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self.logic.processStartTRECalculation()
        self._parameterNode.SetParameter("TRECalculating", "true")

    def onPushStopTRE(self):
        msg = self.logic._commandsData["START_TRE_CALCULATION_STOP"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self.logic.processStopTRECalculation()
        self._parameterNode.SetParameter("TRECalculating", "false")

    def onPushVisFRE(self):
        if not self.ui.pathDigLandmarks.currentPath:
            slicer.util.errorDisplay("Please select digitized landmarks file first!")
            return
        if not self.ui.pathRegResult.currentPath:
            slicer.util.errorDisplay("Please select registration result file first!")
            return
        self.logic.processVisFRE(
            self.ui.pathDigLandmarks.currentPath.strip(),
            self.ui.pathPlanLandmarks.currentPath.strip(),
            self.ui.pathRegResult.currentPath.strip(),
        )

    def onPushPlanLandmarks(self):
        self.updateParameterNodeFromGUI()
        self.logic.processPushPlanLandmarks(
            self._parameterNode.GetNodeReference("LandmarksMarkups")
        )

    def onPushDigitize(self):
        self.updateParameterNodeFromGUI()
        msg = self.logic._commandsData["START_AUTO_DIGITIZE"]
        self.logic._connections.utilSendCommand(msg)

    def onPushDigHighlighted(self):
        self.updateParameterNodeFromGUI()
        self.logic.processDigHilight()

    def onPushDigPrevAndDigHilight(self):
        self.logic.processDigPrevAndDigHilight()

    def onPushDigPrev(self):
        msg = self.logic._commandsData["START_LANDMARK_DIG_PREV"]
        self.logic._connections.utilSendCommand(msg)

    def onLandmarkWidgetHilightChange(self, idx):
        self._parameterNode.SetParameter("LandmarkWidgetHilightIdx", str(idx))
        print("Highlighted the " + str(idx + 1) + "th landmark")

    def onPushRegistration(self):
        self.updateParameterNodeFromGUI()
        msg = self.logic._commandsData["START_REGISTRATION"]
        self.logic._connections.utilSendCommand(msg)
        data = self.logic._connections.receiveMsg()
        print("Registration residual: " + str(data) + "mm")
        slicer.util.infoDisplay("Registration residual: " + str(data) + "mm")

    def onPushUsePreviousRegistration(self):
        self.updateParameterNodeFromGUI()
        msg = self.logic._commandsData["START_USE_PREV_REGISTRATION"]
        self.logic._connections.utilSendCommand(msg)
        data = self.logic._connections.receiveMsg()
        print("Registration residual: " + str(data) + "mm")
        slicer.util.infoDisplay("Registration residual: " + str(data) + "mm")

    def onPushICPDigitize(self):
        msg = self.logic._commandsData["ICP_DIGITIZE"]
        self.logic._connections.utilSendCommand(msg)

    def onPushICPClearPrev(self):
        msg = self.logic._commandsData["ICP_CLEAR_PREV"]
        self.logic._connections.utilSendCommand(msg)

    def onPushICPClearPoints(self):
        msg = self.logic._commandsData["ICP_CLEAR_ALL"]
        self.logic._connections.utilSendCommand(msg)

    def onPushICPRegister(self):
        if not self.ui.pathICPMesh.currentPath:
            slicer.util.errorDisplay("Please select mesh file first!")
            return
        msg = self.logic._commandsData["ICP_REGISTER"]
        self.logic._connections.utilSendCommand(
            msg + "_" + self.ui.pathICPMesh.currentPath.strip()
        )

    def onPushShowICPPoints(self):
        if not self.ui.pathICPPoints.currentPath:
            slicer.util.errorDisplay("Please select digitized landmarks file first!")
            return
        if not self.ui.pathICPReg.currentPath:
            slicer.util.errorDisplay("Please select registration result file first!")
            return
        self.logic.processVisICP(
            self.ui.pathICPPoints.currentPath.strip(),
            self.ui.pathICPReg.currentPath.strip(),
            self.ui.checkIgnoreICP.checked,
        )

    def onPushToolPosePlan(self):
        self.updateParameterNodeFromGUI()
        self.logic.processPushToolPosePlan(self.ui.markupsToolPosePlan.currentNode())

    def onPushToolPoseExternalStart(self):
        self.logic._connections._flag_receiving_nnblc = True
        self.logic._connections.receiveTimerCallBack()
        self._parameterNode.SetParameter("TRECalculating", "true")

    def onPushToolPoseExternalEnd(self):
        self.logic._connections._flag_receiving_nnblc = False
        self._parameterNode.SetParameter("TRECalculating", "false")

    def onPushToolPosePlanRand(self):
        self.updateParameterNodeFromGUI()
        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            self.logic.processPushToolPosePlan(
                self.ui.markupsToolPosePlan.currentNode()
            )

        self.logic.processPushToolPosePlanRand()

    def onPushPlanGrid(self):
        self.updateParameterNodeFromGUI()
        self.logic.processPlanGrid()

    def onPushGridSetNext(self):
        self.updateParameterNodeFromGUI()
        self.logic.processGridSetNext()

    def onPushGridClear(self):
        if self._parameterNode.GetParameter("GridPlanIndicatorNumPrev"):
            prevnum = int(
                float(self._parameterNode.GetParameter("GridPlanIndicatorNumPrev"))
            )
            for i in range(prevnum):
                gridPlanTransform = self._parameterNode.GetNodeReference(
                    "GridPlanTransformNum" + str(i)
                )
                if gridPlanTransform:
                    slicer.mrmlScene.RemoveNode(gridPlanTransform)

                gridPlanIndicator = self._parameterNode.GetNodeReference(
                    "GridPlanIndicatorNum" + str(i)
                )
                if gridPlanIndicator:
                    slicer.mrmlScene.RemoveNode(gridPlanIndicator)

        gridPlanPoints = self._parameterNode.GetNodeReference("GridPlanPoints")
        if gridPlanPoints:
            slicer.mrmlScene.RemoveNode(gridPlanPoints)
            self._parameterNode.SetNodeReferenceID("GridPlanPoints", None)

    def onPushBackForward(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPosePos"))
        self.logic.processManualAdjustTool([0.0, change, 0.0, 0.0, 0.0, 0.0])

    def onPushCloseAway(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPosePos"))
        self.logic.processManualAdjustTool([0.0, 0.0, change, 0.0, 0.0, 0.0])

    def onPushLeftRight(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPosePos"))
        self.logic.processManualAdjustTool([change, 0.0, 0.0, 0.0, 0.0, 0.0])

    def onPushPitch(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPoseRot"))
        self.logic.processManualAdjustTool(
            [0.0, 0.0, 0.0, change / 180.0 * math.pi, 0.0, 0.0]
        )

    def onPushRoll(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPoseRot"))
        self.logic.processManualAdjustTool(
            [0.0, 0.0, 0.0, 0.0, change / 180.0 * math.pi, 0.0]
        )

    def onPushYaw(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustToolPoseRot"))
        self.logic.processManualAdjustTool(
            [0.0, 0.0, 0.0, 0.0, 0.0, change / 180.0 * math.pi]
        )

    def onPushBackForwardReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPosePos"))
        self.logic.processManualAdjustReg(
            [0.0, change, 0.0, 0.0, 0.0, 0.0], self.ui.pathICPPoints.currentPath.strip()
        )

    def onPushCloseAwayReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPosePos"))
        self.logic.processManualAdjustReg(
            [0.0, 0.0, change, 0.0, 0.0, 0.0], self.ui.pathICPPoints.currentPath.strip()
        )

    def onPushLeftRightReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPosePos"))
        self.logic.processManualAdjustReg(
            [change, 0.0, 0.0, 0.0, 0.0, 0.0], self.ui.pathICPPoints.currentPath.strip()
        )

    def onPushPitchReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPoseRot"))
        self.logic.processManualAdjustReg(
            [0.0, 0.0, 0.0, change / 180.0 * math.pi, 0.0, 0.0],
            self.ui.pathICPPoints.currentPath.strip(),
        )

    def onPushRollReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPoseRot"))
        self.logic.processManualAdjustReg(
            [0.0, 0.0, 0.0, 0.0, change / 180.0 * math.pi, 0.0],
            self.ui.pathICPPoints.currentPath.strip(),
        )

    def onPushYawReg(self):
        change = float(self._parameterNode.GetParameter("ManualAdjustRegPoseRot"))
        self.logic.processManualAdjustReg(
            [0.0, 0.0, 0.0, 0.0, 0.0, change / 180.0 * math.pi],
            self.ui.pathICPPoints.currentPath.strip(),
        )

    def onRadioToolRotOptions(self):
        self.updateParameterNodeFromGUI()
        if self._parameterNode.GetNodeReference("TargetPoseTransform"):
            self.logic.processToolPosePlanMeshReCheck()

    def onPushRetrieveToolPose(self):
        if self.ui.pathToolPose.currentPath:
            self.logic.processRetrieveToolPose(self.ui.pathToolPose.currentPath)
        else:
            slicer.util.errorDisplay("Please select a file first!")

    def onPushOverlayHeatMap(self):
        if not self.ui.textMEPValueHeatMapOverlay.text:
            slicer.util.errorDisplay("Please enter MEP value first!")
            return
        mep = float(self.ui.textMEPValueHeatMapOverlay.text)
        if not self._parameterNode.GetNodeReference("TargetPoseTransform"):
            slicer.util.errorDisplay("Please plan tool pose first!")
            return
        targetPoseTransform = vtk.vtkMatrix4x4()
        print("Target pose transform: ")
        self._parameterNode.GetNodeReference(
            "TargetPoseTransform"
            # "TargetPoseTransformCortex"
        ).GetMatrixTransformToParent(targetPoseTransform)
        print(targetPoseTransform)
        if not self._parameterNode.GetNodeReference("InputMeshBrain"):
            slicer.util.errorDisplay("Please select brain mesh first!")
            return
        inmodel = self._parameterNode.GetNodeReference("InputMeshBrain")

        self.logic.processHeatMapOnBrain(mep, targetPoseTransform, inmodel)

    def onPushResetCortex(self):
        inmodel = self._parameterNode.GetNodeReference("InputMeshBrain")
        self.logic.processResetCortex(inmodel)

    def onPushUniformColoring(self):
        inmodel = self._parameterNode.GetNodeReference("InputMeshBrain")
        self.logic.processUniformColoring(inmodel)
