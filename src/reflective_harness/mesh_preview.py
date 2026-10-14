"""Local diagnostic renderer; not EditHero's official renderer."""
import sys
from pathlib import Path
import vtk

def main():
    root=Path(sys.argv[1]);output=Path(sys.argv[2])
    for i in range(1,6):
        path=root/f'turn{i:02d}.glb'
        importer=vtk.vtkGLTFImporter();importer.SetFileName(str(path))
        window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(640,640)
        importer.SetRenderWindow(window);importer.Update()
        renderer=window.GetRenderers().GetFirstRenderer();renderer.SetBackground(.94,.94,.94)
        renderer.ResetCamera();camera=renderer.GetActiveCamera();camera.Azimuth(25);camera.Elevation(15);renderer.ResetCameraClippingRange()
        window.Render();capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.Update()
        writer=vtk.vtkPNGWriter();writer.SetFileName(str(output/f'turn{i:02d}.png'));writer.SetInputConnection(capture.GetOutputPort());writer.Write();window.Finalize()
if __name__=='__main__':main()
