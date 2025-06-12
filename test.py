import meshio
mesh = meshio.read("concrete_model_ordered_elements.dat", file_format="calculix")
meshio.write("concrete_model_ordered_elements.vtk", mesh)