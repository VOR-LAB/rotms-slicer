import os
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import sys
import Loader as L


class Simulation(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Simulation"
        self.parent.categories = ["RoTMS"]
        self.parent.dependencies = []
        self.parent.contributors = ["Jiaming Zhang (Johns Hopkins University)"]
        self.parent.helpText = """
This module provides TMS visualization and control functionality.
"""
        self.parent.acknowledgementText = """
This work was supported by your funding source.
"""
        self.parent = parent

    # def setup(self):
    #     ScriptedLoadableModule.setup(self)

    # def cleanup(self):
    #     ScriptedLoadableModule.cleanup(self)


class SimulationLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual computation done by your module.
    The interface should be such that other python code can import this class and make
    use of the functionality without requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """
    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    def process(self, inputVolume, outputVolume, imageThreshold, invert=False, showResult=True):
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param imageThreshold: values above/below this threshold will be set to 0
        :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
        :param showResult: show output volume in slice viewers
        """
        if not inputVolume or not outputVolume:
            raise ValueError("Input or output volume is invalid")

        import time
        startTime = time.time()
        logging.info('Processing started')

        # Compute the thresholded output volume using the "Threshold Scalar Volume" CLI module
        cliParams = {
            'InputVolume': inputVolume.GetID(),
            'OutputVolume': outputVolume.GetID(),
            'ThresholdValue': imageThreshold,
            'ThresholdType': 'Above' if invert else 'Below'
        }
        cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None,
                                 cliParams, wait_for_completion=True, update_display=showResult)
        # We don't need the CLI module node anymore, remove it to not clutter the scene with it
        slicer.mrmlScene.RemoveNode(cliNode)

        stopTime = time.time()
        logging.info('Processing completed in {0:.2f} seconds'.format(
            stopTime-startTime))


class SimulationWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.guiMessages = True
        self.consoleMessages = True
        self.showGMButton = None
        self.example_path = "example_data"  # Default example path

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # IGTL connections
        self.IGTLNode = slicer.vtkMRMLIGTLConnectorNode()
        slicer.mrmlScene.AddNode(self.IGTLNode)
        self.IGTLNode.SetName('TextConnector')
        self.IGTLNode.SetTypeClient('localhost', 18945)
        # this will activate the the status of the connection:
        self.IGTLNode.Start()
        # self.IGTLNode.RegisterIncomingMRMLNode(self.textNode)
        self.IGTLNode.PushOnConnect()

        self.textNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTextNode', 'TextMessage')
        self.textNode.SetForceCreateStorageNode(True)
        observer = self.textNode.AddObserver(slicer.vtkMRMLTextNode.TextModifiedEvent, self.newText)

        # Create GUI elements directly
        self.collapsibleButton = ctk.ctkCollapsibleButton()
        self.collapsibleButton.text = "TMS Visualization"
        self.layout.addWidget(self.collapsibleButton)
        self.formLayout = qt.QFormLayout(self.collapsibleButton)
        
        def onLoadExampleClicked():
            fileDialog = qt.QFileDialog()
            fileDialog.setFileMode(qt.QFileDialog.Directory)
            if fileDialog.exec_():
             selectedFile = fileDialog.selectedFiles()[0]
             L.Loader.loadExample(selectedFile)

        self.loadExampleButton = qt.QPushButton("Load Example", self.collapsibleButton)
        self.formLayout.addRow(self.loadExampleButton)
        self.loadExampleButton.clicked.connect(onLoadExampleClicked)

        self.meshButton = qt.QCheckBox("Show Mesh", self.collapsibleButton)
        self.meshButton.checked = True
        self.formLayout.addRow(self.meshButton)
        self.meshButton.stateChanged.connect(L.Loader.showMesh)

        self.vouleRenderingButton = qt.QCheckBox("Show Volume Rendering", self.collapsibleButton)
        self.vouleRenderingButton.checked = False
        self.formLayout.addRow(self.vouleRenderingButton)
        self.vouleRenderingButton.stateChanged.connect(L.Loader.showVolumeRendering)

        self.fiberButton = qt.QCheckBox("Show Fibers", self.collapsibleButton)
        self.fiberButton.checked = False
        self.formLayout.addRow(self.fiberButton)
        self.fiberButton.stateChanged.connect(L.Loader.showFibers)

        self.layout.addStretch(1)
        # Create grid layout for matrix input field
        self.collapsibleButton3 = ctk.ctkCollapsibleButton()
        self.collapsibleButton3.text = "Manual Coil Positioning"
        self.layout.addWidget(self.collapsibleButton3)
        self.gridLayout = qt.QGridLayout(self.collapsibleButton3)

        # Create labels for each matrix element
        # Eszter, this is not useful for our purpose, consider deleting it in future
        labels = ["X", "Y", "Z"]
        for i in range(3):
            label = qt.QLabel(labels[i])
            self.gridLayout.addWidget(label, 0, i+1)
            label = qt.QLabel(labels[i])
            self.gridLayout.addWidget(label, i+1, 0)

        # Create line edits for each matrix element
        self.matrixInputs = []
        for i in range(3):
            row = []
            for j in range(4):
                matrixInput = qt.QLineEdit()
                matrixInput.setFixedSize(50, 30)  # Set fixed size for QLineEdit widget
                row.append(matrixInput)
                self.gridLayout.addWidget(matrixInput, i+1, j+1)
                 # Connect the editingFinished signal of each QLineEdit to updateMatrix function
                #matrixInput.editingFinished.connect(lambda: L.Loader.updateMatrix(self))
            self.matrixInputs.append(row)


        # Create label to display current matrix position
        self.currentMatrixLabel = qt.QLabel("Current Matrix Position: ", self.collapsibleButton3)
        self.layout.addWidget(self.currentMatrixLabel)
        # Create label to display matrix elements as text
        self.matrixTextLabel = qt.QLabel("", self.collapsibleButton3)
        self.layout.addWidget(self.matrixTextLabel)

        #Until this line

        self.initialScalarArray = None
        self.layout.addStretch(1)

    def newText(self, caller, event):
        self.t = slicer.mrmlScene.GetNodeByID('vtkMRGMMLTextNode')
        self.example_path = self.t.GetText()
        # Update the loadExampleButton connection with the new example_path
        self.loadExampleButton.clicked.disconnect()
        self.loadExampleButton.clicked.connect(lambda: L.Loader.loadExample(self.example_path))

    def logMessage(self, *args):
        if self.consoleMessages:
            for arg in args:
                print(arg)
        if self.guiMessages:
            if len(self.log.html) > 1024 * 256:
                self.log.clear()
                self.log.insertHtml("Log cleared\n")
            for arg in args:
                self.log.insertHtml(arg)
            self.log.insertPlainText('\n')
            self.log.ensureCursorVisible()
            self.log.repaint()


#
# SimulationTest
#

class SimulationTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_Simulation1()

    def test_Simulation1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Test the module logic
        logic = SimulationLogic()

        # Test the module widget
        widget = SimulationWidget()
        widget.setup()

        self.delayDisplay('Test passed!')


#
# Simulation initialization
#

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        import unittest
        unittest.main(argv=sys.argv[1:])
    else:
        # Create and register the module
        module = Simulation(None)
        module.setup()

