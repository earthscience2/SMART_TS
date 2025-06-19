import logging
from ccx2paraview import Converter
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
c = Converter( "frd/C000001/2025061215.frd", ['vtu'])
c.run()