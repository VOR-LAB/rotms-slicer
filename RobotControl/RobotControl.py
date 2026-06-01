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

import os
import json
import logging
import math
import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from RobotControlLib.UtilConnections import UtilConnections
from RobotControlLib.UtilFormat import utilNumStrFormat

#
# RobotControl
#


class RobotControl(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Robot Control"
        self.parent.categories = ["RoTMS"]
        # TODO: add here list of module names that this module requires
        self.parent.dependencies = []
        self.parent.contributors = ["Yihao Liu (Johns Hopkins University)"]
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", appStartUpPostAction)


def appStartUpPostAction():
    return

#
# RobotControlWidget
#


class RobotControlWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        # needed for parameter node observation
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/RobotControl.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = RobotControlLogic(self.resourcePath('Configs/'))

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene,
                         slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.sliderRotation.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.sliderTranslation.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.checkBoxSafe.connect(
            "toggled(bool)", self.updateParameterNodeFromGUI)

        # Buttons

        self.ui.pushModuleTargetViz.connect(
            'clicked(bool)', self.onPushModuleTargetViz)
        self.ui.pushModuleMedImgPlan.connect(
            'clicked(bool)', self.onPushModuleMedImgPlan)
        self.ui.pushModuleSimulation.connect(
            'clicked(bool)', self.onPushModuleSimulation)

        self.ui.pushSessionReinit.connect(
            'clicked(bool)', self.onPushSessionReinit)

        self.ui.pushConnectRob.connect('clicked(bool)', self.onPushConnectRob)
        self.ui.pushDisconnectRob.connect(
            'clicked(bool)', self.onPushDisconnectRob)

        self.ui.pushGetJntSetInit.connect(
            'clicked(bool)', self.onPushGetJntSetInit)
        self.ui.pushGetJntAngs.connect('clicked(bool)', self.onPushGetJntAngs)
        self.ui.pushGetEFFPose.connect('clicked(bool)', self.onPushGetEFFPose)

        self.ui.pushExecute.connect('clicked(bool)', self.onPushExecute)
        self.ui.pushConfirm.connect('clicked(bool)', self.onPushConfirm)

        self.ui.pushRobotHoming.connect(
            'clicked(bool)', self.onPushRobotHoming)
        self.ui.pushReInit.connect('clicked(bool)', self.onPushReInit)
        self.ui.pushReOffset.connect('clicked(bool)', self.onPushReOffset)

        self.ui.pushBackward.connect('clicked(bool)', self.onPushBackward)
        self.ui.pushCloser.connect('clicked(bool)', self.onPushCloser)
        self.ui.pushFarther.connect('clicked(bool)', self.onPushFarther)
        self.ui.pushForward.connect('clicked(bool)', self.onPushForward)
        self.ui.pushLeft.connect('clicked(bool)', self.onPushLeft)
        self.ui.pushPitch.connect('clicked(bool)', self.onPushPitch)
        self.ui.pushRight.connect('clicked(bool)', self.onPushRight)
        self.ui.pushRoll.connect('clicked(bool)', self.onPushRoll)
        self.ui.pushYaw.connect('clicked(bool)', self.onPushYaw)

        self.ui.pushEndAndBack.connect('clicked(bool)', self.onPushEndAndBack)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()
        self.logic._connections.clear()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(
            self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

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
        self.ui.sliderRotation.value = float(
            self._parameterNode.GetParameter("RotationAdjustmentValue"))
        self.ui.sliderTranslation.value = float(
            self._parameterNode.GetParameter("TranslationAdjustmentValue"))
        self.ui.checkBoxSafe.checked = (
            self._parameterNode.GetParameter("SafeCheck") == "true")

        # Update buttons states and tooltips
        if self._parameterNode.GetParameter("SafeCheck") == "true":
            self.ui.pushExecute.toolTip = "Push button to move robot to an offset location"
            self.ui.pushExecute.enabled = True
            self.ui.pushConfirm.toolTip = "Push button to move robot to planned location"
            self.ui.pushConfirm.enabled = True
            self.ui.pushBackward.toolTip = "Move tool backwards"
            self.ui.pushBackward.enabled = True
            self.ui.pushCloser.toolTip = "Move tool closer"
            self.ui.pushCloser.enabled = True
            self.ui.pushFarther.toolTip = "Move tool farther"
            self.ui.pushFarther.enabled = True
            self.ui.pushForward.toolTip = "Move tool forwards"
            self.ui.pushForward.enabled = True
            self.ui.pushLeft.toolTip = "Move tool left"
            self.ui.pushLeft.enabled = True
            self.ui.pushPitch.toolTip = "Pitch tool"
            self.ui.pushPitch.enabled = True
            self.ui.pushRight.toolTip = "Move tool right"
            self.ui.pushRight.enabled = True
            self.ui.pushRoll.toolTip = "Roll tool"
            self.ui.pushRoll.enabled = True
            self.ui.pushYaw.toolTip = "Yaw tool"
            self.ui.pushYaw.enabled = True
        else:
            self.ui.pushExecute.toolTip = "Safety not checked"
            self.ui.pushExecute.enabled = False
            self.ui.pushConfirm.toolTip = "Safety not checked"
            self.ui.pushConfirm.enabled = False
            self.ui.pushBackward.toolTip = "Safety not checked"
            self.ui.pushBackward.enabled = False
            self.ui.pushCloser.toolTip = "Safety not checked"
            self.ui.pushCloser.enabled = False
            self.ui.pushFarther.toolTip = "Safety not checked"
            self.ui.pushFarther.enabled = False
            self.ui.pushForward.toolTip = "Safety not checked"
            self.ui.pushForward.enabled = False
            self.ui.pushLeft.toolTip = "Safety not checked"
            self.ui.pushLeft.enabled = False
            self.ui.pushPitch.toolTip = "Safety not checked"
            self.ui.pushPitch.enabled = False
            self.ui.pushRight.toolTip = "Safety not checked"
            self.ui.pushRight.enabled = False
            self.ui.pushRoll.toolTip = "Safety not checked"
            self.ui.pushRoll.enabled = False
            self.ui.pushYaw.toolTip = "Safety not checked"
            self.ui.pushYaw.enabled = False

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

        self._parameterNode.SetParameter(
            "RotationAdjustmentValue", str(self.ui.sliderRotation.value))
        self._parameterNode.SetParameter(
            "TranslationAdjustmentValue", str(self.ui.sliderTranslation.value))
        self._parameterNode.SetParameter(
            "SafeCheck", "true" if self.ui.checkBoxSafe.checked else "false")

        self._parameterNode.EndModify(wasModified)

    def onPushModuleMedImgPlan(self):
        slicer.util.selectModule("MedImgPlan")

    def onPushModuleTargetViz(self):
        slicer.util.selectModule("TargetVisualization")

    def onPushModuleSimulation(self):
        slicer.util.selectModule("Simulation")

    def onPushSessionReinit(self):
        msg = self.logic._commandsData["SESSION_REINIT"]
        self.logic._connections.utilSendCommand(msg)

    def onPushConnectRob(self):
        msg = self.logic._commandsData["ROB_CONN_ON"]
        self.logic._connections.utilSendCommand(msg)

    def onPushDisconnectRob(self):
        msg = self.logic._commandsData["ROB_CONN_OFF"]
        self.logic._connections.utilSendCommand(msg)

    def onPushGetJntAngs(self):
        msg = self.logic._commandsData["GET_JNT_ANGS"]
        self.logic._connections.utilSendCommand(msg)
        data = self.logic._connections.receiveMsg()
        print(data)

    def onPushGetEFFPose(self):
        msg = self.logic._commandsData["GET_EFF_POSE"]
        self.logic._connections.utilSendCommand(msg)
        data = self.logic._connections.receiveMsg()
        print(data)

    def onPushGetJntSetInit(self):
        msg = self.logic._commandsData["GET_JNT_ANGS_TOINIT"]
        self.logic._connections.utilSendCommand(msg)
        data = self.logic._connections.receiveMsg()
        print(data)

    def onPushExecute(self):
        msg = self.logic._commandsData["EXECUTE_MOTION"]
        self.logic._connections.utilSendCommand(msg)

    def onPushConfirm(self):
        msg = self.logic._commandsData["EXECUTE_MOVE_CONFIRM"]
        self.logic._connections.utilSendCommand(msg)

    def onPushEndAndBack(self):
        msg = self.logic._commandsData["EXECUTE_ENDBACK"]
        self.logic._connections.utilSendCommand(msg)

    def onPushRobotHoming(self):
        msg = self.logic._commandsData["EXECUTE_ROB_HOMING"]
        self.logic._connections.utilSendCommand(msg)

    def onPushReInit(self):
        msg = self.logic._commandsData["EXECUTE_BACKINIT"]
        self.logic._connections.utilSendCommand(msg)

    def onPushReOffset(self):
        msg = self.logic._commandsData["EXECUTE_BACKOFFSET"]
        self.logic._connections.utilSendCommand(msg)

    def onPushBackward(self):
        self.logic.utilManualAdjust("backward",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushCloser(self):
        self.logic.utilManualAdjust("closer",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushFarther(self):
        self.logic.utilManualAdjust("farther",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushForward(self):
        self.logic.utilManualAdjust("forward",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushLeft(self):
        self.logic.utilManualAdjust("left",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushPitch(self):
        self.logic.utilManualAdjust("pitch",
            float(self._parameterNode.GetParameter("RotationAdjustmentValue")))

    def onPushRight(self):
        self.logic.utilManualAdjust("right",
            float(self._parameterNode.GetParameter("TranslationAdjustmentValue")))

    def onPushRoll(self):
        self.logic.utilManualAdjust("roll",
            float(self._parameterNode.GetParameter("RotationAdjustmentValue")))

    def onPushYaw(self):
        self.logic.utilManualAdjust("yaw",
            float(self._parameterNode.GetParameter("RotationAdjustmentValue")))

#
# RobotControlLogic
#


class RobotControlLogic(ScriptedLoadableModuleLogic):
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
        self._connections = UtilConnections(configPath, "RobotControl")
        self._connections.setup()

        with open(self._configPath+"CommandsConfig.json") as f:
            self._commandsData = (json.load(f))["RobCtrlCmd"]

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("RotationAdjustmentValue"):
            # default 0.5 degree adjustment
            parameterNode.SetParameter("RotationAdjustmentValue", "0.5")
        if not parameterNode.GetParameter("TranslationAdjustmentValue"):
            # default 5 mm adjustment
            parameterNode.SetParameter("TranslationAdjustmentValue", "5.0")
        if not parameterNode.GetParameter("SafeCheck"):
            parameterNode.SetParameter("SafeCheck", "false")

    def utilManualAdjust(self, cmdstr, value):
        if cmdstr == "backward":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_0.0_" + utilNumStrFormat(value/1000.0, decimal=10) + "_0.0")
        if cmdstr == "closer":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_0.0_0.0_" + utilNumStrFormat(-value/1000.0, decimal=10))
        if cmdstr == "farther":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_0.0_0.0_" + utilNumStrFormat(value/1000.0, decimal=10))
        if cmdstr == "forward":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_0.0_" + utilNumStrFormat(-value/1000.0, decimal=10) + "_0.0")
        if cmdstr == "left":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_" + utilNumStrFormat(value/1000.0, decimal=10) + "_0.0_0.0")
        if cmdstr == "pitch":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_R"] + "_" + utilNumStrFormat(value/180.0*math.pi, decimal=10) + "_0.0_0.0")
        if cmdstr == "right":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_T"] + "_" + utilNumStrFormat(-value/1000.0, decimal=10) + "_0.0_0.0")
        if cmdstr == "roll":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_R"] + "_0.0_" + utilNumStrFormat(value/180.0*math.pi, decimal=10) + "_0.0")
        if cmdstr == "yaw":
            self._connections.utilSendCommand(
                self._commandsData["MAN_ADJUST_R"] + "_0.0_0.0_" + utilNumStrFormat(value/180.0*math.pi, decimal=10))
