import os
import json
import vtk, qt, ctk, slicer, sitkUtils
from slicer.ScriptedLoadableModule import *
import numpy as np
from vtk.util.numpy_support import vtk_to_numpy
from vtk.util.numpy_support import numpy_to_vtk
import SimpleITK as sitk
import timeit

class Mapper:
    def __init__(self, config=None):
        self.config = config

    @classmethod
    def map(cls, loader, time=True):
        if loader._updating_pose:
            return

        matrixFromFid = vtk.vtkMatrix4x4()
        if loader.coil_mode == 'planned':
            matrixFromFid.DeepCopy(loader.getPlannedMatrix())
            loader.applyCoilMatrix(matrixFromFid)
        else:
            loader.markupsPlaneNode.GetObjectToWorldMatrix(matrixFromFid)
            loader.applyCoilMatrix(matrixFromFid)

        loader.lastCoilMatrix = vtk.vtkMatrix4x4()
        loader.lastCoilMatrix.DeepCopy(matrixFromFid)

        # Update matrix text label in Widget:
        matrixText = ""
        for i in range(3):
            for j in range(4):
                value = matrixFromFid.GetElement(i, j)
                matrixText += "{:.3f} ".format(value)
            matrixText += "\n"
        slicer.modules.SimulationWidget.matrixTextLabel.setText(matrixText)

        if time:
            start = timeit.default_timer()
        # the update transform based on the old transfrom
        # rotate the scalar magnetic field (magnorm)

        DataVec = loader.magfieldGTNode.GetTransformFromParent().GetDisplacementGrid()
        DataVec.SetOrigin(0, 0, 0)
        DataVec.SetSpacing(1, 1, 1)

        # When using a planned pose, there may be a hidden parent transform (e.g. FSModel_brainToWorld).
        # We only want the coil pose relative to the brain, so strip that parent by applying its inverse.
        matrix_for_field = vtk.vtkMatrix4x4()
        matrix_for_field.DeepCopy(matrixFromFid)

        matrix_current = vtk.vtkMatrix4x4() # current transform of the magnetic vector field
        matrix_current.Multiply4x4(matrix_for_field, loader.coilDefaultMatrix, matrix_current)

        matrix_current_inv = vtk.vtkMatrix4x4()
        matrix_current_inv.Invert(matrix_current,matrix_current_inv)
        combined_tfm = vtk.vtkMatrix4x4()

        matrix_ref = vtk.vtkMatrix4x4()
        loader.conductivityNode.GetIJKToRASMatrix(matrix_ref)
        img_ref = loader.conductivityNode.GetImageData()

        matrix_ref.Multiply4x4(matrix_current_inv, matrix_ref, combined_tfm)


        reslice = vtk.vtkImageReslice()
        reslice.SetInputData(DataVec)
        reslice.SetInformationInput(img_ref)
        reslice.SetInterpolationModeToLinear()
        reslice.SetResliceAxes(combined_tfm)
        reslice.TransformInputSamplingOff()
        reslice.Update()
        DataOut = reslice.GetOutput()

        xyz = DataOut.GetDimensions()
        
        # # rotate DataOut vectors
        DataOut_np = vtk_to_numpy(DataOut.GetPointData().GetScalars())
        # # transposed of the rotation matrix
        RotMat_transp = np.array([[matrixFromFid.GetElement(0,0), matrixFromFid.GetElement(1,0),  matrixFromFid.GetElement(2,0)],
                                   [matrixFromFid.GetElement(0,1), matrixFromFid.GetElement(1,1),  matrixFromFid.GetElement(2,1)],
                                   [matrixFromFid.GetElement(0,1), matrixFromFid.GetElement(1,1),  matrixFromFid.GetElement(2,1)]])
        # # rotate the vector field
        DataOut_np_rot = np.matmul(DataOut_np, RotMat_transp)
        # # reshape the numpy array
        DataOut_np_rot = np.reshape(DataOut_np_rot,(xyz[0], xyz[1], xyz[2], 3))

        # Downcast to float before sending over IGTL to keep transfers fast and avoid UI stalls
        DataOut_np_rot = DataOut_np_rot.astype(np.float32, copy=False)

        VTK_array = numpy_to_vtk(DataOut_np_rot.ravel(), deep=True, array_type=vtk.VTK_FLOAT)
        DataOut.GetPointData().SetScalars(VTK_array)
        DataOut.GetPointData().GetScalars().SetNumberOfComponents(3)

        loader.magfieldNode.SetAndObserveImageData(DataOut)
        # Queue the IGTL push so the UI thread is not blocked by large sends
        qt.QTimer.singleShot(0, lambda n=loader.magfieldNode: loader.IGTLNode.PushNode(n))


        # time in seconds:
        if time:
            stop = timeit.default_timer()
            execution_time = stop - start
            # print("Resampling + Mapping Executed in " + str(execution_time) + " seconds.")
            print(execution_time)

    @staticmethod
    def mapElectricfieldToMesh(scalarNode, brainNode, coilMatrix):
        print("mapElectricfieldToMesh executed. THIS IS NEW CODE")
        # get the scalar range from image scalars
        rng = scalarNode.GetImageData().GetScalarRange()
        fMin = rng[0]
        fMax = rng[1]

        # Transform the model into the volume's IJK space
        modelTransformerRasToIjk = vtk.vtkTransformFilter()
        transformRasToIjk = vtk.vtkTransform()
        m = vtk.vtkMatrix4x4()
        scalarNode.GetRASToIJKMatrix(m)
        transformRasToIjk.SetMatrix(m)
        modelTransformerRasToIjk.SetTransform(transformRasToIjk)
        modelTransformerRasToIjk.SetInputConnection(brainNode.GetMeshConnection())

        probe = vtk.vtkProbeFilter()
        probe.SetSourceData(scalarNode.GetImageData())
        probe.SetInputConnection(modelTransformerRasToIjk.GetOutputPort())
        # transform model back to ras
        modelTransformerIjkToRas = vtk.vtkTransformFilter()
        modelTransformerIjkToRas.SetTransform(transformRasToIjk.GetInverse())
        modelTransformerIjkToRas.SetInputConnection(probe.GetOutputPort())
        modelTransformerIjkToRas.Update()


        brainNode.SetAndObserveMesh(modelTransformerIjkToRas.GetOutput())

        #----
        # --- target point on cortex under coil + scalar readout ---

        polyData = brainNode.GetPolyData()
        if not polyData or polyData.GetNumberOfPoints() == 0:
            print("No cortex polydata")
            return

        coil_center = [coilMatrix.GetElement(0,3),
               coilMatrix.GetElement(1,3),
               coilMatrix.GetElement(2,3)]

        # pick a direction; if this misses, flip the sign
        coil_dir = [-coilMatrix.GetElement(0,2),
            -coilMatrix.GetElement(1,2),
            -coilMatrix.GetElement(2,2)]

        n = (coil_dir[0]**2 + coil_dir[1]**2 + coil_dir[2]**2) ** 0.5
        if n < 1e-8:
            print("Invalid coil direction")
            return
        coil_dir = [coil_dir[0]/n, coil_dir[1]/n, coil_dir[2]/n]

#--- here

        # --- intersect ray with cortex mesh (robust: try both directions) ---
        ray_len = 200.0
        candidates = []

        for sgn in (1.0, -1.0):
            ray_end = [
            coil_center[0] + sgn * coil_dir[0] * ray_len,
            coil_center[1] + sgn * coil_dir[1] * ray_len,
            coil_center[2] + sgn * coil_dir[2] * ray_len,
            ]
            ipts = vtk.vtkPoints()
            obb = vtk.vtkOBBTree()
            obb.SetDataSet(polyData)
            obb.BuildLocator()
            hit = obb.IntersectWithLine(coil_center, ray_end, ipts, None)
            if hit and ipts.GetNumberOfPoints() > 0:
                p = ipts.GetPoint(0)
                d2 = vtk.vtkMath.Distance2BetweenPoints(coil_center, p)
                candidates.append((d2, p))

        if not candidates:
            print("No cortex intersection in either direction")
            return

        # closest intersection to the coil center
        cortex_point = min(candidates, key=lambda x: x[0])[1]

        # snap to closest mesh vertex
        pl = vtk.vtkPointLocator()
        pl.SetDataSet(polyData)
        pl.BuildLocator()
        pid = pl.FindClosestPoint(cortex_point)
        # v = 0.0

        arr = polyData.GetPointData().GetScalars()
        if arr is None:
            print("No scalars on cortex mesh")
            return

        # Collect heatmap values for all planned grid points (if available).
        medimgParameterNode = slicer.mrmlScene.GetSingletonNode(
            "MedImgPlan", "vtkMRMLScriptedModuleNode"
        )
        if not medimgParameterNode:
            try:
                candidate = slicer.util.getNode("MedImgPlan")
                if candidate and candidate.IsA("vtkMRMLScriptedModuleNode"):
                    medimgParameterNode = candidate
            except Exception:
                medimgParameterNode = None
        gridPlanPointsNode = None
        currentTargetLabel = "N/A"

        if medimgParameterNode:
            gridPlanPointsNode = medimgParameterNode.GetNodeReference("GridPlanPoints")
            currentAt = medimgParameterNode.GetParameter("GridPlanCurrentAt")
            if currentAt not in (None, ""):
                try:
                    currentTargetLabel = "G-" + str(int(float(currentAt)))
                except ValueError:
                    currentTargetLabel = "G-" + str(currentAt)

        if not gridPlanPointsNode:
            gridPlanPointsNode = slicer.util.getFirstNodeByName("GridPlanPoints")

        heatmapValues = {}
        nearestGridLabel = None
        nearestGridDistance2 = None
        if gridPlanPointsNode:
            for i in range(gridPlanPointsNode.GetNumberOfControlPoints()):
                gridPoint = [0.0, 0.0, 0.0]
                gridPlanPointsNode.GetNthControlPointPosition(i, gridPoint)
                gridPid = pl.FindClosestPoint(gridPoint)
                label = str(i+1)
                heatmapValues[label] = round(float(arr.GetTuple1(gridPid)), 6)

                d2 = vtk.vtkMath.Distance2BetweenPoints(cortex_point, gridPoint)
                if nearestGridDistance2 is None or d2 < nearestGridDistance2:
                    nearestGridDistance2 = d2
                    nearestGridLabel = label

        if currentTargetLabel == "N/A" and nearestGridLabel:
            currentTargetLabel = nearestGridLabel

        heatmapValuesJson = json.dumps(heatmapValues)
        if medimgParameterNode:
            medimgParameterNode.SetParameter("GridHeatmapValuesJson", heatmapValuesJson)

        tableNode = slicer.util.getFirstNodeByName("GridHeatmapValues")
        if not tableNode or not tableNode.IsA("vtkMRMLTableNode"):
            tableNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLTableNode", "GridHeatmapValues"
            )

        table = tableNode.GetTable()
        table.Initialize()

        targetColumn = vtk.vtkStringArray()
        targetColumn.SetName("Target")
        valueColumn = vtk.vtkDoubleArray()
        valueColumn.SetName("HeatmapValue")
        table.AddColumn(targetColumn)
        table.AddColumn(valueColumn)
        table.SetNumberOfRows(len(heatmapValues))

        for row, (label, value) in enumerate(heatmapValues.items()):
            table.SetValue(row, 0, vtk.vtkVariant(str(label)))
            table.SetValue(row, 1, vtk.vtkVariant(float(value)))

        if medimgParameterNode:
            medimgParameterNode.SetNodeReferenceID(
                "GridHeatmapValuesTable", tableNode.GetID()
            )

        # valid = polyData.GetPointData().GetArray("vtkValidPointMask")
        # if valid is not None and valid.GetTuple1(pid) < 0.5:
        #     # Fallback: sample the volume at cortex_point by converting RAS->IJK and clamping
        #     rasToIjk = vtk.vtkMatrix4x4()
        #     scalarNode.GetRASToIJKMatrix(rasToIjk)

        #     ras = [cortex_point[0], cortex_point[1], cortex_point[2], 1.0]
        #     ijk4 = [0.0, 0.0, 0.0, 0.0]
        #     rasToIjk.MultiplyPoint(ras, ijk4)

        #     ijk = [int(round(ijk4[0])), int(round(ijk4[1])), int(round(ijk4[2]))]

        #     img = scalarNode.GetImageData()
        #     dims = img.GetDimensions()
        #     ijk[0] = max(0, min(dims[0]-1, ijk[0]))
        #     ijk[1] = max(0, min(dims[1]-1, ijk[1]))
        #     ijk[2] = max(0, min(dims[2]-1, ijk[2]))

        #     # For scalar volumes this works; for vector volumes you’ll need GetScalarComponentAsDouble per component
        #     v = img.GetScalarComponentAsDouble(ijk[0], ijk[1], ijk[2], 0)
        #     print("TargetPointOnCortex (RAS):", cortex_point, " scalar(fallback@clamped IJK):", v)
        #     return
        print("########")
        print("Current target:", currentTargetLabel)
        print("Heatmap values:", json.dumps(heatmapValues))
        #---
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        view.cornerAnnotation().SetText(
            vtk.vtkCornerAnnotation.UpperLeft,
            "Simulated E-field Intensity ({0}): {1:.2f} V/m".format(
                currentTargetLabel, arr.GetTuple1(pid)
            ),
        )
        view.cornerAnnotation().GetTextProperty().SetColor(1.0,0,0)
        view.forceRender()
        
        probedPointScalars = probe.GetOutput().GetPointData().GetScalars()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(probe.GetOutputPort())

        # activate scalars
        brainNode.GetDisplayNode().SetActiveScalarName('ImageScalars')
        
        # select color scheme for scalars
        brainNode.GetDisplayNode().SetAndObserveColorNodeID(slicer.util.getNode('ColdToHotRainbow').GetID())
        brainNode.GetDisplayNode().ScalarVisibilityOn()
        brainNode.GetDisplayNode().SetScalarRange(fMin, fMax)

        # color legend for brain scalars:
        colorLegendDisplayNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(brainNode)
        colorLegendDisplayNode.SetTitleText("EVec")
        colorLegendDisplayNode.SetLabelFormat("%7.8f")


    @staticmethod
    def modifyIncomingImage(loader):
        print("modifyIncomingImage executes")
        matrix_ref = vtk.vtkMatrix4x4()
        loader.conductivityNode.GetIJKToRASMatrix(matrix_ref)
        loader.pyigtlNode.ApplyTransformMatrix(matrix_ref)

        # this part will need to be done with the resampling (it only maps the incoming pyigtl image to the brain):
        if hasattr(loader, "lastCoilMatrix") and loader.lastCoilMatrix is not None:
            Mapper.mapElectricfieldToMesh(loader.pyigtlNode, loader.modelNode, loader.lastCoilMatrix)
        else:
            print("No lastCoilMatrix yet (call Mapper.map once first)")

        # Jump to maximum point of E field
        pyigtl_data_image = sitkUtils.PullVolumeFromSlicer(loader.pyigtlNode)
        pyigtl_data_array = sitk.GetArrayFromImage(pyigtl_data_image)

        max_idx = np.squeeze(np.where(pyigtl_data_array==pyigtl_data_array.max()))
        max_point = pyigtl_data_image.TransformIndexToPhysicalPoint([int(max_idx[2]), int(max_idx[1]), int(max_idx[0])])
        max_point = np.array([-max_point[0], -max_point[1], max_point[2]]) #IJK to RAS

        slicer.vtkMRMLSliceNode.JumpAllSlices(slicer.mrmlScene, *max_point[0:3])


        
