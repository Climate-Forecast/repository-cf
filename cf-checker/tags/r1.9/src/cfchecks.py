#!/usr/bin/env python
#-------------------------------------------------------------
# Name: cfchecks.py
#
# Author: Rosalyn Hatcher - Met Office, UK
#
# Maintainer: Rosalyn Hatcher - NCAS-CMS, Univ. of Reading, UK
#
# Date: February 2003
#
# Version: @release@
#
#-------------------------------------------------------------
''' cfchecker [-s|--cf_standard_names standard_names.xml] [-u|--udunits udunits.dat] file1 [file2...]

Description:
 The cfchecker checks NetCDF files for compliance to the CF standard.
 
Options:
 -s or --cf_standard_names:
       the location of the CF standard name table (xml)
       
 -u or --udunits:
       the location of the udunits.dat file

 -h or --help: Prints this help text.

'''

from sys import *
import cdms, re, string, types, Numeric, udunits

from cdms.axis import FileAxis
from cdms.auxcoord import FileAuxAxis1D

STANDARDNAME="./standard_name.xml"

#-----------------------------------------------------------
from xml.sax import ContentHandler
from xml.sax import make_parser
from xml.sax.handler import feature_namespaces


def normalize_whitespace(text):
    "Remove redundant whitespace from a string."
    return ' '.join(text.split())

class ConstructDict(ContentHandler):
    """Parse the xml standard_name table, reading all entries
       into a dictionary; storing standard_name and units.
    """
    def __init__(self):
        self.inUnitsContent = 0
        self.inEntryIdContent = 0
        self.inVersionNoContent = 0
        self.inLastModifiedContent = 0
        self.dict = {}
        
    def startElement(self, name, attrs):
        # If it's an entry element, save the id
        if name == 'entry':
            id = normalize_whitespace(attrs.get('id', ""))
            self.this_id = id

        # If it's the start of a canonical_units element
        elif name == 'canonical_units':
            self.inUnitsContent = 1
            self.units = ""

        elif name == 'alias':
            id = normalize_whitespace(attrs.get('id', ""))
            self.this_id = id

        elif name == 'entry_id':
            self.inEntryIdContent = 1
            self.entry_id = ""

        elif name == 'version_number':
            self.inVersionNoContent = 1
            self.version_number = ""

        elif name == 'last_modified':
            self.inLastModifiedContent = 1
            self.last_modified = ""
            

    def characters(self, ch):
        if self.inUnitsContent:
            self.units = self.units + ch

        elif self.inEntryIdContent:
            self.entry_id = self.entry_id + ch

        elif self.inVersionNoContent:
            self.version_number = self.version_number + ch

        elif self.inLastModifiedContent:
            self.last_modified = self.last_modified + ch

    def endElement(self, name):
        # If it's the end of the canonical_units element, save the units
        if name == 'canonical_units':
            self.inUnitsContent = 0
            self.units = normalize_whitespace(self.units)
            self.dict[self.this_id] = self.units
            
        # If it's the end of the entry_id element, find the units for the self.alias
        elif name == 'entry_id':
            self.inEntryIdContent = 0
            self.entry_id = normalize_whitespace(self.entry_id)
            self.dict[self.this_id] = self.dict[self.entry_id]

        # If it's the end of the version_number element, save it
        elif name == 'version_number':
            self.inVersionNoContent = 0
            self.version_number = normalize_whitespace(self.version_number)

        # If it's the end of the last_modified element, save the last modified date
        elif name == 'last_modified':
            self.inLastModifiedContent = 0
            self.last_modified = normalize_whitespace(self.last_modified)


def chkDerivedName(name):
    """Checks whether name is a derived standard name and adheres
       to the transformation rules. See CF standard names document
       for more information.
    """
    if re.search("^(direction|magnitude|square|divergence)_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^rate_of_change_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^(grid_)?(northward|southward|eastward|westward)_derivative_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^product_of_[a-zA-Z][a-zA-Z0-9_]*_and_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^ratio_of_[a-zA-Z][a-zA-Z0-9_]*_to_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^derivative_of_[a-zA-Z][a-zA-Z0-9_]*_wrt_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^(correlation|covariance)_over_[a-zA-Z][a-zA-Z0-9_]*_of_[a-zA-Z][a-zA-Z0-9_]*_and_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^histogram_over_[a-zA-Z][a-zA-Z0-9_]*_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^probability_distribution_over_[a-zA-Z][a-zA-Z0-9_]*_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0

    if re.search("^probability_density_function_over_[a-zA-Z][a-zA-Z0-9_]*_of_[a-zA-Z][a-zA-Z0-9_]*$",name):
        return 0
    
    # Not a valid derived name
    return 1


#======================
# Checking class
#======================
class CFChecker:
    
  def __init__(self, uploader=None, useFileName="yes", badc=None, coards=None, cfStandardNamesXML=None, udunitsDat=''):
      self.uploader = uploader
      self.useFileName = useFileName
      self.badc = badc
      self.coards = coards
      self.standardNames = cfStandardNamesXML
      self.udunits = udunitsDat
      self.err = 0
      self.warn = 0
      #rc = self.Checker(file)

  def checker(self, file):
    # Set up dictionary of all valid attributes, their type and use
    self.setUpAttributeList()
    fileSuffix = re.compile('^\S+\.nc$')

    lowerVars=[]
    rc=1

    print ""
    if self.uploader:
        realfile = string.split(file,".nc")[0]+".nc"
        print "CHECKING NetCDF FILE:", realfile
    elif self.useFileName=="no":
        print "CHECKING NetCDF FILE"
    else:
        print "CHECKING NetCDF FILE:",file
    print "====================="
    
    # Check for valid filename
    if not fileSuffix.match(file):
        print "ERROR: Filename should have .nc suffix"
        exit(0)

    # Initialisation of udunits package
    udunits.utInit(self.udunits)

    # Set up dictionary of standard_names and their assoc. units
    parser = make_parser()
    parser.setFeature(feature_namespaces, 0)
    self.std_name_dh = ConstructDict()
    parser.setContentHandler(self.std_name_dh)
    parser.parse(self.standardNames)

    print "Using Standard Name Table Version "+self.std_name_dh.version_number+" ("+self.std_name_dh.last_modified+")"
    print ""
    
    # Read in netCDF file
    try:
        self.f=cdms.open(file,"r")
    except:
        print "\nCould not open file, please check that NetCDF is formatted correctly.\n".upper()
        print "ERRORS detected:",1
        exit()

    # Check global attributes
    if not self.chkGlobalAttributes(): rc=0
        
    (coordVars,auxCoordVars,boundsVars,climatologyVars,gridMappingVars)=self.getCoordinateDataVars()
    self.coordVars = coordVars
    self.auxCoordVars = auxCoordVars
    self.boundsVars = boundsVars
    self.climatologyVars = climatologyVars
    self.gridMappingVars = gridMappingVars
    
    allCoordVars=coordVars[:]
    allCoordVars[len(allCoordVars):]=auxCoordVars[:]
    self.setUpFormulas()
    axes=self.f.axes.keys()

    
    # Check each variable
    for var in self.f._file_.variables.keys():
        print ""
        print "------------------"
        print "Checking variable:",var
        print "------------------"

        if not self.validName(var):
            print "ERROR: Invalid variable name -",var
            self.err = self.err+1
            rc=0

        # Check to see if a variable with this name already exists (case-insensitive)
        lowerVar=var.lower()
        if lowerVar in lowerVars:
            print "WARNING: variable clash:-",var
            self.warn = self.warn + 1
        else:
            lowerVars.append(lowerVar)

        if var not in axes:
            # Non-coordinate variable
            if not self.chkDimensions(var,allCoordVars): rc=0
        
        if not self.chkDescription(var): rc=0

        for attribute in self.f[var].attributes.keys():
            if not self.chkAttribute(attribute,var,allCoordVars): rc=0

        if not self.chkUnits(var,allCoordVars): rc=0
        
        if not self.chkValidMinMaxRange(var): rc=0

        if not self.chk_FillValue(var): rc=0

        if not self.chkAxisAttribute(var): rc=0

        if not self.chkPositiveAttribute(var): rc=0

        if not self.chkCellMethods(var): rc=0

        if not self.chkCellMeasures(var): rc=0
        
        if not self.chkFormulaTerms(var): rc=0

        if not self.chkCompressAttr(var): rc=0

        if not self.chkPackedData(var): rc=0

        if var in coordVars:
            if not self.chkMultiDimCoord(var, axes): rc=0
            if not self.chkValuesMonotonic(var): rc=0

        if var in gridMappingVars:
            if not self.chkGridMappingVar(var) : rc=0

        if var in axes:
            # Check var is a FileAxis.  If not then there may be a problem with its declaration.
            # I.e. Multi-dimensional coordinate var with a dimension of the same name
            # or an axis that hasn't been identified through the coordinates attribute
            # CRM035 (17.04.07)
            if not (isinstance(self.f[var], FileAxis) or isinstance(self.f[var], FileAuxAxis1D)):
                print "WARNING: Possible incorrect declaration of a coordinate variable.\n See Section 5 of the Conventions document."
                self.warn = self.warn+1
            else:    
                if self.f[var].isTime():
                    if not self.chkTimeVariableAttributes(var): rc=0

    print ""
    print "ERRORS detected:",self.err
    print "WARNINGS given:",self.warn


  #-----------------------------
  def setUpAttributeList(self):
  #-----------------------------
      """Set up Dictionary of valid attributes, their corresponding
      Type; S(tring) or N(umeric) and Use C(oordinate),
      D(ata non-coordinate) or G(lobal) variable."""
    
      self.AttrList={}
      self.AttrList['add_offset']=['N','D']
      self.AttrList['ancillary_variables']=['S','D']
      self.AttrList['axis']=['S','C']
      self.AttrList['bounds']=['S','C']
      self.AttrList['calendar']=['S','C']
      self.AttrList['cell_measures']=['S','D']
      self.AttrList['cell_methods']=['S','D']
      self.AttrList['climatology']=['S','C']
      self.AttrList['comment']=['S',('G','D')]
      self.AttrList['compress']=['S','C']
      self.AttrList['Conventions']=['S','G']
      self.AttrList['coordinates']=['S','D']
      self.AttrList['_FillValue']=['N','D']
      self.AttrList['flag_meanings']=['S','D']
      self.AttrList['flag_values']=['S','D']
      self.AttrList['formula_terms']=['S','C']
      self.AttrList['grid_mapping']=['S','D']
      self.AttrList['history']=['S','G']
      self.AttrList['institution']=['S',('G','D')]
      self.AttrList['leap_month']=['N','C']
      self.AttrList['leap_year']=['N','C']
      self.AttrList['long_name']=['S',('C','D')]
      self.AttrList['missing_value']=['N','D']
      self.AttrList['month_lengths']=['N','C']
      self.AttrList['positive']=['S','C']
      self.AttrList['references']=['S',('G','D')]
      self.AttrList['scale_factor']=['N','D']
      self.AttrList['source']=['S',('G','D')]
      self.AttrList['standard_error_multiplier']=['N','D']
      self.AttrList['standard_name']=['S',('C','D')]
      self.AttrList['title']=['S','G']
      self.AttrList['units']=['S',('C','D')]
      self.AttrList['valid_max']=['N',('C','D')]
      self.AttrList['valid_min']=['N',('C','D')]
      self.AttrList['valid_range']=['N',('C','D')]
      
      return


  #---------------------------
  def uniqueList(self, list):
  #---------------------------
      """Determine if list has any repeated elements."""
      seen={}
      for x in list:
          if seen.has_key(x):
              return 0
          else:
              seen[x]=1
      return 1


  #-------------------------
  def isNumeric(self, var):
  #-------------------------
      """Determine if variable is of Numeric data type."""
      types=['i','f','d']
      rc=1 
      if self.f[var].typecode() not in types:
          rc=0
      return rc


  #--------------------------------------------------
  def getInterpretation(self, units, positive=None):
  #--------------------------------------------------
    """Determine the interpretation (time - T, height or depth - Z,
    latitude - Y or longitude - X) of a dimension."""
    
    udunitsPtr = udunits.utUnit()
    if units in ['level','layer','sigma_level']:
        # Dimensionless vertical coordinate
        return "Z"
    if udunits.utScan(units,udunitsPtr):
        # Don't print this message out o/w it is repeated for every variable
        # that has this dimension.  CRM033 return "None" instead
        # print "ERROR: Invalid units:",units
        #self.err = self.err+1
        return None
    
    # Time Coordinate
    if udunits.utIsTime(udunitsPtr):
        return "T"
    
    # Vertical Coordinate
    if positive and re.match('(up|down)',positive,re.I):
        return "Z"

    # Variable is a vertical coordinate if the units are dimensionally
    # equivalent to Pressure
    fromPtr=udunits.utUnit()
    toPascalPtr=udunits.utUnit()
    udunits.utScan("Pa",toPascalPtr)
    udunits.utScan(units,fromPtr)
    if not udunits.utConvert(fromPtr,toPascalPtr)[0]:
        return "Z"
        
    # Latitude Coordinate
    if re.match('(degrees_north|degree_north|degrees_N|degree_N|degreesN|degreeN)',units):
        return "Y"
        
    # Longitude Coordinate
    if re.match('(degrees_east|degree_east|degrees_E|degree_E|degreesE|degreeE)',units):
        return "X"

    # Not possible to deduce interpretation
    return None


  #--------------------------------
  def getCoordinateDataVars(self):
  #--------------------------------
    """Obtain list of coordinate data variables, boundary
    variables, climatology variables and grid_mapping variables."""
    
    variables=self.f.variables.keys()     # List of variables, but doesn't include coord vars
    allVariables=self.f._file_.variables.keys()   # List of all vars, including coord vars
    axes=self.f.axes.keys()
    
    coordVars=[]
    boundaryVars=[]
    climatologyVars=[]
    gridMappingVars=[]
    auxCoordVars=[]

    for var in allVariables:
        if var not in variables:
            # Coordinate variable - 1D & dimension is the same name as the variable
            coordVars.append(var)

## Commented out 21.02.06 - Duplicate code also in method chkDimensions
## Probably can be completely removed.
##         if var not in coordVars:
##             # Non-coordinate variable so check if it has any repeated dimensions
##             dimensions=self.f[var].getAxisIds()
##             dimensions.sort()
##             if not self.uniqueList(dimensions):
##                 print "ERROR: variable has repeated dimensions"
##                 self.err = self.err+1

        #------------------------
        # Auxilliary Coord Checks
        #------------------------
        if self.f[var].attributes.has_key('coordinates'):
            # Check syntax of 'coordinates' attribute
            if not self.parseBlankSeparatedList(self.f[var].attributes['coordinates']):
                print "ERROR: Invalid syntax for 'coordinates' attribute in",var
                self.err = self.err+1
            else:
                coordinates=string.split(self.f[var].attributes['coordinates'])
                for dataVar in coordinates:
                    if dataVar in variables:

                        auxCoordVars.append(dataVar)

                        # Is the auxillary coordinate var actually a label?
                        if self.f[dataVar].typecode() == 'c':
                            # Label variable
                            if not len(self.f[dataVar].getAxisIds()) == 2:
                                print "ERROR: Label variable",dataVar,"must have 2 dimensions only"
                                self.err = self.err+1

                            if self.f[dataVar].getAxisIds()[0] not in self.f[var].getAxisIds():
                                print "ERROR: Leading dimension of",dataVar,"must match one of those for",var
                                self.err = self.err+1
                        else:
                            # Not a label variable
                            for dim in self.f[dataVar].getAxisIds():
                                if dim not in self.f[var].getAxisIds():
                                    print "ERROR: Dimensions of",dataVar,"must be a subset of dimensions of",var
                                    self.err = self.err+1
                                    break
                    elif dataVar not in allVariables:
                        print "ERROR: coordinates attribute referencing non-existent variable:",dataVar
                        self.err = self.err+1

        #-------------------------
        # Boundary Variable Checks
        #-------------------------
        if self.f[var].attributes.has_key('bounds'):
            bounds=self.f[var].attributes['bounds']
            # Check syntax of 'bounds' attribute
            if not re.search("^[a-zA-Z0-9_]*$",bounds):
                print "ERROR: Invalid syntax for 'bounds' attribute"
                self.err = self.err+1
            else:
                if bounds in variables:
                    boundaryVars.append(bounds)

                    if not self.isNumeric(bounds):
                        print "ERROR: boundary variable with non-numeric data type"
                        self.err = self.err+1
                    if len(self.f[var].shape) + 1 == len(self.f[bounds].shape):
                        if var in axes:
                            varDimensions=[var]
                        else:
                            varDimensions=self.f[var].getAxisIds()

                        for dim in varDimensions:
                            if dim not in self.f[bounds].getAxisIds():
                                print "ERROR: Incorrect dimensions for boundary variable:",bounds
                                self.err = self.err+1
                    else:
                        print "ERROR: Incorrect number of dimensions for boundary variable:",bounds
                        self.err = self.err+1

                    if self.f[bounds].attributes.has_key('units'):
                        if self.f[bounds].attributes['units'] != self.f[var].attributes['units']:
                            print "ERROR: Boundary var",bounds,"has inconsistent units to",var
                            self.err = self.err+1
                    if self.f[bounds].attributes.has_key('standard_name'):
                        if self.f[bounds].attributes['standard_name'] != self.f[var].attributes['standard_name']:
                            print "ERROR: Boundary var",bounds,"has inconsistent std_name to",var
                            self.err = self.err+1
                else:
                    print "ERROR: bounds attribute referencing non-existent variable:",bounds
                    self.err = self.err+1
            # Check that points specified by a coordinate or auxilliary coordinate
            # variable should lie within, or on the boundary, of the cells specified by
            # the associated boundary variable.
            if bounds in variables:
                # Is boundary variable 2 dimensional?  If so can check that points
                # lie within, or on the boundary.
                if len(self.f[bounds].getAxisIds()) <= 2:
                    varData=self.f[var].getValue()
                    boundsData=self.f[bounds].getValue()
##                    if len(varData) == 1:
                    if type(varData) == type(1) or type(varData) == type(1.00) or len(varData) == 1:
                        # Gone for belts and braces approach here!!
                        # Variable contains only one value
                        # Bounds array will be 1 dimensional
                        if not ((varData <= boundsData[0] and varData >= boundsData[1])
                                or (varData >= boundsData[0] and varData <= boundsData[1])):
                            print "WARNING: Data for variable",var,"lies outside cell boundaries"
                            self.warn = self.warn+1
                    else:
                        i=0
                        for value in varData:
                            if not ((value <= boundsData[i][0] and value >= boundsData[i][1]) \
                                    or (value >= boundsData[i][0] and value <= boundsData[i][1])):
                                print "WARNING: Data for variable",var,"lies outside cell boundaries"
                                self.warn = self.warn+1
                                break
                            i=i+1

        #----------------------------
        # Climatology Variable Checks
        #----------------------------
        if self.f[var].attributes.has_key('climatology'):
            climatology=self.f[var].attributes['climatology']
            # Check syntax of 'climatology' attribute
            if not re.search("^[a-zA-Z0-9_]*$",climatology):
                print "ERROR: Invalid syntax for 'climatology' attribute"
                self.err = self.err+1
            else:
                if climatology in variables:
                    climatologyVars.append(climatology)
                    if not self.isNumeric(climatology):
                        print "ERROR: climatology variable with non-numeric data type"
                        self.err = self.err+1
                    if self.f[climatology].attributes.has_key('units'):
                        if self.f[climatology].attributes['units'] != self.f[var].attributes['units']:
                            print "ERROR: Climatology var",climatology,"has inconsistent units to",var
                            self.err = self.err+1
                    if self.f[climatology].attributes.has_key('standard_name'):
                        if self.f[climatology].attributes['standard_name'] != self.f[var].attributes['standard_name']:
                            print "ERROR: Climatology var",climatology,"has inconsistent std_name to",var
                            self.err = self.err+1
                    if self.f[climatology].attributes.has_key('calendar'):
                        if self.f[climatology].attributes['calendar'] != self.f[var].attributes['calendar']:
                            print "ERROR: Climatology var",climatology,"has inconsistent calendar to",var
                            self.err = self.err+1
                else:
                    print "ERROR: climatology attribute referencing non-existent variable"
                    self.err = self.err+1

        #------------------------------------------
        # Is there a grid_mapping variable?
        #------------------------------------------
        if self.f[var].attributes.has_key('grid_mapping'):
            grid_mapping = self.f[var].attributes['grid_mapping']
            # Check syntax of grid_mapping attribute: a string whose value is a single variable name.
            if not re.search("^[a-zA-Z0-9_]*$",grid_mapping):
                print "ERROR:",var,"- Invalid syntax for 'grid_mapping' attribute"
                self.err = self.err+1
            else:
                if grid_mapping in variables:
                    gridMappingVars.append(grid_mapping)
                else:
                    print "ERROR: grid_mapping attribute referencing non-existent variable",grid_mapping
                    self.err = self.err+1
                    
    return (coordVars, auxCoordVars, boundaryVars, climatologyVars, gridMappingVars)


  #-------------------------------------
  def chkGridMappingVar(self, varName):
  #-------------------------------------
      """Section 5.6: Grid Mapping Variable Checks"""
      rc=1
      var=self.f[varName]
      
      if var.attributes.has_key('grid_mapping_name'):
          # Check grid_mapping_name is valid
          validNames = ['albers_conical_equal_area','azimuthal_equidistant','lambert_azimuthal_equal_area',
                        'lambert_conformal_conic','polar_stereographic','rotated_latitude_longitude',
                        'stereographic','transverse_mercator']
          
          if var.grid_mapping_name not in validNames:
              print "ERROR: Invalid grid_mapping_name:",var.grid_mapping_name
              self.err = self.err+1
              rc=0
      else:
          print "ERROR: No grid_mapping_name attribute set"
          self.err = self.err+1
          rc=0
              
      if len(var.getAxisIds()) != 0:
          print "WARNING: grid_mapping_variable should have 0 dimensions"
          self.warn = self.warn+1

      return rc


  #------------------------
  def setUpFormulas(self):
  #------------------------
      """Set up dictionary of all valid formulas"""
      self.formulas={}
      self.alias={}
      self.alias['atmosphere_ln_pressure_coordinate']='atmosphere_ln_pressure_coordinate'
      self.alias['atmosphere_sigma_coordinate']='sigma'
      self.alias['sigma']='sigma'
      self.alias['atmosphere_hybrid_sigma_pressure_coordinate']='hybrid_sigma_pressure'
      self.alias['hybrid_sigma_pressure']='hybrid_sigma_pressure'
      self.alias['atmosphere_hybrid_height_coordinate']='atmosphere_hybrid_height_coordinate'
      self.alias['ocean_sigma_coordinate']='ocean_sigma_coordinate'
      self.alias['ocean_s_coordinate']='ocean_s_coordinate'
      self.alias['ocean_sigma_z_coordinate']='ocean_sigma_z_coordinate'
      self.alias['ocean_double_sigma_coordinate']='ocean_double_sigma_coordinate'
      

      self.formulas['atmosphere_ln_pressure_coordinate']=['p(k)=p0*exp(-lev(k))']
      self.formulas['sigma']=['p(n,k,j,i)=ptop+sigma(k)*(ps(n,j,i)-ptop)']

      self.formulas['hybrid_sigma_pressure']=['p(n,k,j,i)=a(k)*p0+b(k)*ps(n,j,i)'
                                              ,'p(n,k,j,i)=ap(k)+b(k)*ps(n,j,i)']

      self.formulas['atmosphere_hybrid_height_coordinate']=['z(n,k,j,i)=a(k)+b(k)*orog(n,j,i)']

      self.formulas['ocean_sigma_coordinate']=['z(n,k,j,i)=eta(n,j,i)+sigma(k)*(depth(j,i)+eta(n,j,i))']
      
      self.formulas['ocean_s_coordinate']=['z(n,k,j,i)=eta(n,j,i)*(1+s(k))+depth_c*s(k)+(depth(j,i)-depth_c)*C(k)'
                                           ,'C(k)=(1-b)*sinh(a*s(k))/sinh(a)+b*[tanh(a*(s(k)+0.5))/(2*tanh(0.5*a))-0.5]']

      self.formulas['ocean_sigma_z_coordinate']=['z(n,k,j,i)=eta(n,j,i)+sigma(k)*(min(depth_c,depth(j,i))+eta(n,j,i))'
                                                 ,'z(n,k,j,i)=zlev(k)']

      self.formulas['ocean_double_sigma_coordinate']=['z(k,j,i)=sigma(k)*f(j,i)'
                                                      ,'z(k,j,i)=f(j,i)+(sigma(k)-1)*(depth(j,i)-f(j,i))'
                                                      ,'f(j,i)=0.5*(z1+z2)+0.5*(z1-z2)*tanh(2*a/(z1-z2)*(depth(j,i)-href))']


  #----------------------------------------
  def parseBlankSeparatedList(self, list):
  #----------------------------------------
      """Parse blank separated list"""
      if re.match("^[a-zA-Z0-9_ ]*$",list):
          return 1
      else:
          return 0


  #------------------------------
  def chkGlobalAttributes(self):
  #------------------------------
    """Check validity of global attributes."""
    rc=1
    if self.f.attributes.has_key('Conventions'):
        if self.f.attributes['Conventions'] != "CF-1.0":
            print "ERROR: This netCDF file does not appear to contain CF Convention data."
            print "See section 2.6.1 of the convention documentation."
            self.err = self.err+1
            rc=0
    else:
        print "WARNING: No 'Conventions' attribute present"
        self.warn = self.warn+1
        rc=1

    for attribute in ['title','history','institution','source','reference','comment']:
        if self.f.attributes.has_key(attribute):
            if type(self.f.attributes[attribute]) != types.StringType:
                print "ERROR: Global attribute",attribute,"must be of type 'String'"
                self.err = self.err+1
    return rc


  #--------------------------
  def validName(self, name):
  #--------------------------
    """ Check for valid name.  They must begin with a
    letter and be composed of letters, digits and underscores."""

    nameSyntax = re.compile('^[a-zA-Z][a-zA-Z0-9_]*$')
    if not nameSyntax.match(name):
        return 0

    return 1


  #---------------------------------------------
  def chkDimensions(self,varName,allcoordVars):
  #---------------------------------------------
    """Check variable has non-repeated dimensions, that
       space/time dimensions are listed in the order T,Z,Y,X
       and that any non space/time dimensions are added to
       the left of the space/time dimensions, unless it
       is a boundary variable or climatology variable, where
       1 trailing dimension is allowed."""

    var=self.f[varName]
    dimensions=var.getAxisIds()
    trailingVars=[]
    
    if len(dimensions) > 1:
        order=['T','Z','Y','X']
        axesFound=[0,0,0,0] # Holding array to record whether a dimension with an axis value has been found.
        i=-1
        lastPos=-1
        trailing=0   # Flag to indicate trailing dimension
        
        # Flags to hold positions of first space/time dimension and
        # last Non-space/time dimension in variable declaration.
        firstST=-1
        lastNonST=-1
        nonSpaceDimensions=[]
        
## Commented out for CRM #022
##        validTrailing=self.boundsVars[:]
##        validTrailing[len(validTrailing):]=self.climatologyVars[:]

        for dim in dimensions:
            i=i+1
            try:
                if hasattr(self.f[dim],'axis'):
                    pos=order.index(self.f[dim].axis)

                    # Is there already a dimension with this axis attribute specified.
                    if axesFound[pos] == 1:
                        print "ERROR: Variable has more than 1 coordinate variable with same axis value"
                        self.err = self.err+1
                    else:
                        axesFound[pos] = 1
                else:
                    # Determine interpretation of variable by units attribute
                    if hasattr(self.f[dim],'positive'):
                        interp=self.getInterpretation(self.f[dim].units,self.f[dim].positive)
                    else:
                        interp=self.getInterpretation(self.f[dim].units)

                    if not interp: raise ValueError
                    pos=order.index(interp)

                if firstST == -1:
                    firstST=pos
            except AttributeError:
                print "ERROR: Problem accessing variable:",dim,"(May not exist in file)."
                self.err = self.err+1
                exit(0)
            except ValueError:
                # Dimension is not T,Z,Y or X axis
                nonSpaceDimensions.append(dim)
                trailingVars.append(dim)
                lastNonST=i
            else:
                # Is the dimensional position of this dimension further to the right than the previous dim?
                if pos >= lastPos:
                    lastPos=pos
                    trailingVars=[]
                else:
                    print "WARNING: space/time dimensions appear in incorrect order"
                    self.warn = self.warn+1

## Removed this check (See CRM #022)
## This check should only be applied for COARDS conformance. (Addition of --coards flag would be useful here)
##         if lastNonST > firstST and firstST != -1:
##             if len(trailingVars) == 1:
##                 if var.id not in validTrailing:
##                     print "WARNING: dimensions",nonSpaceDimensions,"should appear to left of space/time dimensions"
##                     self.warn = self.warn+1
##             else:
##                 print "WARNING: dimensions",nonSpaceDimensions,"should appear to left of space/time dimensions"
##                 self.warn = self.warn+1
                
        dimensions.sort()
        if not self.uniqueList(dimensions):
            print "ERROR: variable has repeated dimensions"
            self.err = self.err+1

## Removed this check as per emails 11 June 2004 (See CRM #020)
##     # Check all dimensions of data variables have associated coordinate variables
##     for dim in dimensions:
##         if dim not in f._file_.variables.keys() or dim not in allcoordVars:
##             if dim not in trailingVars:
##                 # dim is not a valid trailing dimension. (valid trailing dimensions e.g. for bounds
##                 # vars; do not need to have an associated coordinate variable CF doc 7.1)
##                 print "WARNING: Dimension:",dim,"does not have an associated coordinate variable"
##                 self.warn = self.warn+1


  #-------------------------------------------------------
  def chkAttribute(self, attribute,varName,allCoordVars):
  #-------------------------------------------------------
    """Check the syntax of the attribute name, that the attribute
    is of the correct type and that it is attached to the right
    kind of variable."""
    rc=1
    var=self.f[varName]
    
    if not self.validName(attribute):
        print "ERROR: Invalid attribute name -",attribute
        self.err = self.err+1
        return 0

    value=var.attributes[attribute]

    #------------------------------------------------------------
    # Attribute of wrong 'type' in the sense numeric/non-numeric
    #------------------------------------------------------------
    if self.AttrList.has_key(attribute):
        # Standard Attribute, therefore check type
        
        attrType=type(value)
        if attrType == types.StringType:
            attrType='S'
        elif attrType == types.IntType or attrType == types.FloatType:
            attrType='N'
        elif attrType == type(Numeric.array([])):
            attrType='N'
        elif attrType == types.NoneType:
            attrType=self.AttrList[attribute][0]
        else:
            print "Unknown Type for attribute:",attribute,attrType

        if self.AttrList[attribute][0] != attrType:
            print "ERROR: Attribute",attribute,"of incorrect type"
            self.err = self.err+1
            rc=0


        # Attribute attached to the wrong kind of variable
        uses=self.AttrList[attribute][1]
        usesLen=len(uses)
        i=1
        for use in uses:
            if use == "C" and var.id in allCoordVars:
                # Valid association
                break
            elif use == "D" and var.id not in allCoordVars:
                # Valid association
                break
            elif i == usesLen:
                if attribute == "missing_value" and var.missing_value:
                    print "WARNING: attribute",attribute,"attached to wrong kind of variable"
                    self.warn = self.warn+1
            else:
                i=i+1


        # Check no time variable attributes. E.g. calendar, month_lengths etc.
        TimeAttributes=['calendar','month_lengths','leap_year','leap_month','climatology']
        if attribute in TimeAttributes:

            if var.attributes.has_key('units'):
                udunitsPtr=udunits.utUnit()
                udunits.utScan(var.attributes['units'],udunitsPtr)
                if not udunits.utIsTime(udunitsPtr):
                    print "ERROR: Attribute",attribute,"may only be attached to time coordinate variable"
                    self.err = self.err+1
                    rc=0
            else:        
                print "ERROR: Attribute",attribute,"may only be attached to time coordinate variable"
                self.err = self.err+1
                rc=0
        
    return rc


  #----------------------------------
  def chkCellMethods(self, varName):
  #----------------------------------
    """Checks on cell_methods attribute
    1) Correct syntax
    2) Valid methods
    3) Valid names
    4) No duplicate entries for dimension other than 'time'"""
    # dim1: [dim2: [dim3: ...]] method [ (comment) ]
    # where comment is of the form:  ([interval: value unit [interval: ...] comment:] remainder)
    rc=1
    error = 0  # Flag to indicate validity of cell_methods string syntax
    varDimensions={}
    var=self.f[varName]
    
    if var.attributes.has_key('cell_methods'):
        cellMethods=var.attributes['cell_methods']
        getComments=re.compile(r'\([^)]+\)')

        # Remove comments from the cell_methods string and split at these points
        noComments=getComments.sub('%5A',cellMethods)
        substrings=re.split('%5A',noComments)
        pr=re.compile(r'^\s*(\S+\s*:\s*(\S+\s*:\s*)*(point|sum|maximum|median|mid_range|minimum|mean|mode|standard_deviation|variance)(\s+(over|within)\s+(days|years))?\s*)+$')
        # Validate each substring
        for s in substrings:
            if s:
                if not pr.match(s):
                    strError=s
                    error=1
                    break

                # Validate dim and check that it only appears once unless it is 'time'
                allDims=re.findall(r'\S+\s*:',s)
                for part in allDims:
                    dims=re.split(':',part)
                    for d in dims:
                        if d:
                            if var.getAxisIndex(d) == -1 and not d in self.std_name_dh.dict.keys():
                                print "ERROR: Invalid 'name' in cell_methods attribute:",d
                                self.err = self.err+1
                                rc=0
                            elif varDimensions.has_key(d) and d != "time":
                                print "WARNING: Multiple cell_methods entries for dimension:",d
                                self.warn = self.warn+1
                            else:
                                varDimensions[d]=1

        # Validate the comment if it is standardized
        ### RSH TO DO:  Still need to implement validation of unit in the standardized comment.
        if not error:
            comments=getComments.findall(cellMethods)
            cpr=re.compile(r'^\((interval:\s+\d+\s+(years|months|days|hours|minutes|seconds)\s*)*(comment: .+)?\)')
            for c in comments:
                if re.search(r'^\(\s*interval',c):
                    # Only need to check standardized comments i.e. those beginning (interval ...)
                    if not cpr.match(c):
                        strError=c
                        error=1
                        break

        if error:
            print "ERROR: Invalid cell_methods syntax: '" + strError + "'"
            self.err = self.err + 1
            rc=0

    return rc


  #----------------------------------
  def chkCellMeasures(self,varName):
  #----------------------------------
    """Checks on cell_measures attribute:
    1) Correct syntax
    2) Reference valid variable
    3) Valid measure"""
    rc=1
    var=self.f[varName]
    
    if var.attributes.has_key('cell_measures'):
        cellMeasures=var.attributes['cell_measures']
        if not re.search("^([a-zA-Z0-9]+: +([a-zA-Z0-9_ ]+:?)*( +[a-zA-Z0-9_]+)?)$",cellMeasures):
            print "ERROR: Invalid cell_measures syntax"
            self.err = self.err+1
            rc=0
        else:
            # Need to validate the measure + name
            split=string.split(cellMeasures)
            splitIter=iter(split)
            try:
                while 1:
                    measure=splitIter.next()
                    variable=splitIter.next()

                    if variable not in self.f.variables.keys():
                        print "ERROR: cell_measures referring to variable that doesn't exist"
                        self.err = self.err+1
                        rc=0
                        
                    else:
                        # Valid variable name in cell_measures so carry on with tests.    
                        if len(self.f[variable].getAxisIds()) > len(var.getAxisIds()):
                            print "ERROR: Dimensions of",variable,"must be same or a subset of",var.getAxisIds()
                            self.err = self.err+1
                            rc=0
                        else:
                            # If cell_measures variable has more dims than var then this check automatically will fail
                            # Put in else so as not to duplicate ERROR messages.
                            for dim in self.f[variable].getAxisIds():
                                if dim not in var.getAxisIds():
                                    print "ERROR: Dimensions of",variable,"must be same or a subset of",var.getAxisIds()
                                    self.err = self.err+1
                                    rc=0
                    
                        measure=re.sub(':','',measure)
                        if not re.match("^(area|volume)$",measure):
                            print "ERROR: Invalid measure in attribute cell_measures"
                            self.err = self.err+1
                            rc=0

                        if measure == "area" and self.f[variable].units != "m2":
                            print "ERROR: Must have square meters for area measure"
                            self.err = self.err+1
                            rc=0

                        if measure == "volume" and self.f[variable].units != "m3":
                            print "ERROR: Must have cubic meters for volume measure"
                            self.err = self.err+1
                            rc=0
                        
            except StopIteration:
                pass
            
    return rc


  #----------------------------------
  def chkFormulaTerms(self,varName):
  #----------------------------------
    """Checks on formula_terms attribute (CF Section 4.3.2):
    formula_terms = var: term var: term ...
    1) No standard_name present
    2) No formula defined for std_name
    3) Invalid formula_terms syntax
    4) Var referenced, not declared"""
    rc=1
    var=self.f[varName]
    
    if var.attributes.has_key('formula_terms'):
        # Get standard_name to determine which formula is to be used
        if not var.attributes.has_key('standard_name'):
            print "ERROR: Cannot get formula definition as no standard_name"
            self.err = self.err+1
            # No sense in carrying on as can't validate formula_terms without valid standard name
            return 0


        stdName=var.attributes['standard_name']
        if not self.alias.has_key(stdName):
            print "ERROR: No formula defined for standard name:",stdName
            self.err = self.err+1
            # No formula available so can't validate formula_terms
            return 0

        index=self.alias[stdName]

        formulaTerms=var.attributes['formula_terms']
        if not re.search("^([a-zA-Z0-9_]+: +[a-zA-Z0-9_]+( +)?)*$",formulaTerms):
            print "ERROR: Invalid formula_terms syntax"
            self.err = self.err+1
            rc=0
        else:
            # Need to validate the term & var
            split=string.split(formulaTerms)
            for x in split[:]:
                if not re.search("^[a-zA-Z0-9_]+:$", x):
                    # Variable - should be declared in netCDF file
                    if x not in self.f._file_.variables.keys():
                        print "ERROR:",x,"is not declared as a variable"
                        self.err = self.err+1
                        rc=0       
                else:
                    # Term - Should be present in formula
                    x=re.sub(':','',x)
                    found='false'
                    for formula in self.formulas[index]:
                        if re.search(x,formula):
                            found='true'
                            break

                    if found == 'false':
                        print "ERROR: term",x,"not present in formula"
                        self.err = self.err+1
                        rc=0

    return rc


  #----------------------------------------
  def chkUnits(self,varName,allCoordVars):
  #----------------------------------------
      """Check units attribute"""
      rc=1
      var=self.f[varName]

      if self.badc:
          rc = self.chkBADCUnits(var)
          # If unit is a BADC unit then no need to check via udunits
          if rc:
              return rc

      if var.attributes.has_key('units'):
          # Type of units is a string
          units = var.attributes['units']
          if type(units) != types.StringType:
              print "ERROR: units attribute must be of type 'String'"
              self.err = self.err+1
              # units not a string so no point carrying out further tests
              return 0
            
          # units - level, layer and sigma_level are deprecated
          if units in ['level','layer','sigma_level']:
              print "WARNING: units",units,"is deprecated"
              self.warn = self.warn+1
          elif units == 'month':
              print "WARNING: The unit 'month', defined by udunits to be exactly year/12, should"
              print "         be used with caution. (CF Section 4.4)"
              self.warn = self.warn+1
          elif units == 'year':
              print "WARNING: The unit 'year', defined by udunits to be exactly 365.242198781 days,"
              print "         should be used with caution. It is not a calendar year. (CF Section 4.4)"
          else:
              # units must be recognizable by udunits package
              varUnitPtr=udunits.utUnit()
              if udunits.utScan(var.attributes['units'],varUnitPtr):
                  print "ERROR: Invalid units: ",var.attributes['units']
                  self.err = self.err+1
                  rc=0
        
              # units of a variable that specifies a standard_name must
              # be consistent with units given in standard_name table
              if var.attributes.has_key('standard_name'):
                  stdName = var.attributes['standard_name']
                  if stdName in self.std_name_dh.dict.keys():
                      # Get canonical units from standard name table
                      stdNameUnits = self.std_name_dh.dict[stdName]
                      canonicalUnitPtr=udunits.utUnit()
                      udunits.utScan(stdNameUnits,canonicalUnitPtr)

                      if var.attributes.has_key('cell_methods'):
                          # Remove comments from the cell_methods string - no need to search these
                          getComments=re.compile(r'\([^)]+\)')
                          noComments=getComments.sub('%5A',var.attributes['cell_methods'])

                          if re.search(r'(\s+|:)variance',noComments):
                              # Variance method so standard_name units need to be squared.
                              unitPtr=udunits.utUnit()
                              udunits.utScan(stdNameUnits,unitPtr)
                              udunits.utMultiply(unitPtr,unitPtr,canonicalUnitPtr)
                              units=udunits.utPrint(canonicalUnitPtr)

                      udunits.utScan(var.attributes['units'],varUnitPtr)
                      equiv = udunits.utConvert(varUnitPtr,canonicalUnitPtr)
                      if equiv[0] != 0:
                          # Conversion unsuccessful
                          print "ERROR: Units are not consistent with those given in the standard_name table."
                          self.err = self.err+1
                          rc=0

      else:

          # No units attribute - is this a coordinate variable or
          # dimensionless vertical coordinate var
          if var.id in allCoordVars:
              # Label variables do not require units attribute
              if self.f[var.id].typecode() != 'c':
                  if var.attributes.has_key('axis'):
                      if not var.axis == 'Z':
                          print "WARNING: units attribute should be present"
                          self.warn = self.warn+1
                      elif not var.attributes.has_key('positive') and not var.attributes.has_key('formula_terms'):
                          print "WARNING: units attribute should be present"
                          self.warn = self.warn+1
                
      return rc


  #----------------------------
  def chkBADCUnits(self, var):
  #----------------------------
      """Check units allowed by BADC"""
      units_lines=open("/usr/local/cf-checker/lib/badc_units.txt").readlines()

      # badc_units test case
      #units_lines=open("/home/ros/SRCE_projects/CF_Checker_W/main/Test_Files/badc_units.txt").readlines()
      
      # units must be recognizable by the BADC units file
      for line in units_lines:
          if hasattr(var, 'units') and var.attributes['units'] in string.split(line):
              print "Valid units in BADC list:", var.attributes['units']
              rc=1
              break
          else:
              rc=0
              
      return rc
  

  #---------------------------------------
  def chkValidMinMaxRange(self, varName):
  #---------------------------------------
      """Check that valid_range and valid_min/valid_max are not both specified"""
      var=self.f[varName]
    
      if var.attributes.has_key('valid_range'):
          if var.attributes.has_key('valid_min') or \
             var.attributes.has_key('valid_max'):

              print "ERROR: Illegal use of valid_range and valid_min/valid_max"
              self.err = self.err+1
              return 0

      return 1


  #---------------------------------
  def chk_FillValue(self, varName):
  #---------------------------------
    """Check 1) type of _FillValue
    2) _FillValue lies outside of valid_range
    3) type of missing_value
    4) flag use of missing_value as deprecated"""
    rc=1
    var=self.f[varName]
    varType=var.typecode()
    if var.__dict__.has_key('_FillValue'):
        fillValue=var.__dict__['_FillValue']
        if varType != fillValue.typecode():
            print "ERROR: _FillValue of different type to variable"
            self.err = self.err+1
            rc=0
            
        if var.attributes.has_key('valid_range'):
            # Check _FillValue is outside valid_range
            validRange=var.attributes['valid_range']
            if fillValue > validRange[0] and fillValue < validRange[1]:
                print "WARNING: _FillValue should be outside valid_range"
                self.warn = self.warn+1

        if var.id in self.boundsVars:
            print "WARNING: Boundary Variable",var.id,"should not have _FillValue attribute"
            self.warn = self.warn+1
        elif var.id in self.climatologyVars:
            print "ERROR: Climatology Variable",var.id,"must not have _FillValue attribute"
            self.err = self.err+1
            rc=0

    if var.attributes.has_key('missing_value'):
        missingValue=var.attributes['missing_value']

        if missingValue:
            if var.__dict__.has_key('_FillValue'):
                if fillValue != missingValue:
                    print "WARNING: missing_value and _FillValue set to differing values"
                    self.warn = self.warn+1
            else:
                # _FillValue not present
                print "WARNING: Use of 'missing_value' attribute is deprecated"
                self.warn = self.warn+1

            missingValueType=missingValue.typecode()
            if varType != missingValueType:
                print "ERROR: missing_value of different type to variable"
                self.err = self.err+1
                rc=0

            if var.id in self.boundsVars:
                print "WARNING: Boundary Variable",var.id,"should not have missing_value attribute"
                self.warn = self.warn+1
            elif var.id in self.climatologyVars:
                print "ERROR: Climatology Variable",var.id,"must not have missing_value attribute"
                self.err = self.err+1
                rc=0
    return rc
        

  #------------------------------------
  def chkAxisAttribute(self, varName):
  #------------------------------------
      """Check validity of axis attribute"""
      var=self.f[varName]
      
      if var.attributes.has_key('axis'):
          if not re.match('^(X|Y|Z|T)$',var.attributes['axis'],re.I):
              print "ERROR: Invalid value for axis attribute"
              self.err = self.err+1
              return 0

          # Check that axis attribute is consistent with the coordinate type
          # deduced from units and positive.
          if hasattr(var,'positive'): 
              interp=self.getInterpretation(var.units,var.positive)
          else:
              interp=self.getInterpretation(var.units)

          if interp != None:
              # It was possible to deduce axis interpretation from units/positive
              if interp != var.axis:
                  print "ERROR: axis attribute inconsistent with coordinate type as deduced from units and/or positive"
                  self.err = self.err+1
                  return 0
            
      return 1


  #----------------------------------------
  def chkPositiveAttribute(self, varName):
  #----------------------------------------
      var=self.f[varName]
      if var.attributes.has_key('positive'):
          if not re.match('^(down|up)$',var.attributes['positive'],re.I):
              print "ERROR: Invalid value for positive attribute"
              self.err = self.err+1
              return 0

      return 1


  #-----------------------------------------
  def chkTimeVariableAttributes(self, varName):
  #-----------------------------------------
    rc=1
    var=self.f[varName]
    
    if var.attributes.has_key('calendar'):
        if not re.match('(gregorian|standard|proleptic_gregorian|noleap|365_day|all_leap|366_day|360_day|julian|none)',
                        var.attributes['calendar'],re.I):
            # Non-standardized calendar so month_lengths should be present
            if not var.attributes.has_key('month_lengths'):
                print "ERROR: Non-standard calendar, so month_lengths attribute must be present"
                self.err = self.err+1
                rc=0
        else:   
            if var.attributes.has_key('month_lengths') or \
               var.attributes.has_key('leap_year') or \
               var.attributes.has_key('leap_month'):
                print "ERROR: The attributes 'month_lengths', 'leap_year' and 'leap_month' must not appear when 'calendar' is present."
                self.err = self.err+1
                rc=0
            
    if var.attributes.has_key('month_lengths'):
        if len(var.attributes['month_lengths']) != 12 and \
           var.attributes['month_lengths'].typecode() != 'i':
            print "ERROR: Attribute 'month_lengths' should be an integer array of size 12"
            self.err = self.err+1
            rc=0

    if var.attributes.has_key('leap_year'):
        if var.attributes['leap_year'].typecode() != 'i' and \
           len(var.attributes['leap_year']) != 1:
            print "ERROR: leap_year should be a scalar value"
            self.err = self.err+1
            rc=0

    if var.attributes.has_key('leap_month'):
        if not re.match("^(1|2|3|4|5|6|7|8|9|10|11|12)$",
                        str(var.attributes['leap_month'][0])):
            print "ERROR: leap_month should be between 1 and 12"
            self.err = self.err+1
            rc=0

        if not var.attributes.has_key('leap_year'):
            print "WARNING: leap_month is ignored as leap_year NOT specified"
            self.warn = self.warn+1

    # Time units must contain a reference time
    udunitsPtr=udunits.utUnit()
    udunits.utScan(var.units,udunitsPtr)
    if udunits.utCalendar(1,udunitsPtr)[0]:
        print "ERROR: Invalid units and/or reference time"
        self.err = self.err+1
        
    return rc

    
  #----------------------------------
  def chkDescription(self, varName):
  #----------------------------------
      """Check 1) standard_name & long_name attributes are present
               2) for a valid standard_name as listed in the standard name table."""
      rc=1
      var=self.f[varName]

      if not var.attributes.has_key('standard_name') and \
         not var.attributes.has_key('long_name'):

          exceptions=self.boundsVars+self.climatologyVars+self.gridMappingVars
          if var.id not in exceptions:
              print "WARNING: No standard_name or long_name attributes"
              self.warn = self.warn+1
              
      if var.attributes.has_key('standard_name'):
          # Check if valid by the standard_name table
          name=var.attributes['standard_name']
          if re.match(".* .?",name) :
              print "ERROR: Whitespace not allowed in standard_name: '"+name+"'"
              self.err = self.err + 1
              rc=0
              
          elif not name in self.std_name_dh.dict.keys():
              if chkDerivedName(name):
                  print "ERROR: Invalid standard_name:",name
                  self.err = self.err + 1
                  rc=0

      return rc


  #-----------------------------------
  def chkCompressAttr(self, varName):
  #-----------------------------------
    rc=1
    var=self.f[varName]
    if var.attributes.has_key('compress'):
        compress=var.attributes['compress']

        if var.typecode() != 'i':
            print "ERROR:",var.id,"- compress attribute can only be attached to variable of type int."
            self.err = self.err+1
            return 0
        if not re.search("^[a-zA-Z0-9_ ]*$",compress):
            print "ERROR: Invalid syntax for 'compress' attribute"
            self.err = self.err+1
            rc=0
        else:
            dimensions=string.split(compress)
            dimProduct=1
            for x in dimensions:
                found='false'
                if x in self.f.dimensions.keys():
                    # Get product of compressed dimension sizes for use later
                    dimProduct=dimProduct*self.f.dimensions[x]
                    found='true'

                if found != 'true':
                    print "ERROR: compress attribute naming nonexistent dimension: ",x
                    self.err = self.err+1
                    rc=0

            values=var.getValue()
            outOfRange=0
            for val in values[:]:
                if val < 0 or val > dimProduct-1:
                    outOfRange=1
                    break;
                
            if outOfRange:
                print "ERROR: values of",var.id,"must be in the range 0 to",dimProduct-1
                self.err = self.err+1
    return rc

  #---------------------------------
  def chkPackedData(self, varName):
  #---------------------------------
    rc=1
    var=self.f[varName]
    if var.attributes.has_key('scale_factor') and var.attributes.has_key('add_offset'):
        if var.attributes['scale_factor'].typecode() != var.attributes['add_offset'].typecode():
            print "ERROR: scale_factor and add_offset must be the same numeric data type"
            self.err = self.err+1
            # No point running rest of packed data tests
            return 0

    if var.attributes.has_key('scale_factor'):
        type=var.attributes['scale_factor'].typecode()
    elif var.attributes.has_key('add_offset'):
        type=var.attributes['add_offset'].typecode()
    else:
        # No packed Data attributes present
        return 1

    # One or other attributes present; run remaining checks
    if var.typecode() != type:
        if type != 'f' and type != 'd':
            print "ERROR: scale_factor and add_offset must be of type float or double"
            self.err = self.err+1
            rc=0

        if var.typecode() != '1' and  var.typecode() != 's' and var.typecode() != 'i':
            print "ERROR:",var.id,"must be of type byte, short or int"
            self.err = self.err+1
            rc=0

        if type == 'f' and var.typecode() == 'i':
            print "WARNING:",var.id,"should not be of type int"
            self.warn = self.warn+1
            
    return rc

  #------------------------------------------
  def chkMultiDimCoord(self, varName, axes):
  #------------------------------------------
      """If a coordinate variable is multi-dimensional, then it is recommended
      that the variable name should not match the name of any of its dimensions."""
      var=self.f[varName]
    
      # This is a temporary work around to obtain the dimensions of the coord
      # var.  In CDMS vn4.0 only 1D coord vars will be axis variables; There
      # will be no need to use _obj_. See CRM #011
      if var.id in axes and len(var._obj_.dimensions) > 1:
          # Multi-dimensional coordinate var
          if var.id in var._obj_.dimensions:
              print "WARNING: The name of a multi-dimensional coordinate variable"
              print "         should not match the name of any of its dimensions."
              self.warn = self.warn + 1

  #--------------------------------------
  def chkValuesMonotonic(self, varName):
  #--------------------------------------
    """A coordinate variable must have values that are strictly monotonic
    (increasing or decreasing)."""
    rc=1
    var=self.f[varName]
    values=var.getValue()
    i=0
    for val in values[:]:
        if i == 0:
            # First value - no comparison to do
            i=i+1
            lastVal=val
            continue
        elif i == 1:
            i=i+1
            if val < lastVal:
                # Decreasing sequence
                type='decr'
            elif val > lastVal:
                # Increasing sequence
                type='incr'
            else:
                # Same value - ERROR
                print "ERROR: co-ordinate variable '" + var.id + "' not monotonic"
                self.err = self.err+1
                return 1

            lastVal=val
        else:
            i=i+1
            if val < lastVal and type != 'decr':
                # ERROR - should be increasing value
                print "ERROR: co-ordinate variable '" + var.id + "' not monotonic"
                self.err = self.err+1
                return 1
            elif val > lastVal and type != 'incr':
                # ERROR - should be decreasing value
                print "ERROR: co-ordinate variable '" + var.id + "' not monotonic"
                self.err = self.err+1
                return 1

            lastVal=val

def getargs(arglist):
    
    '''getargs(arglist): parse command line options and environment variables'''

    from getopt import getopt, GetoptError
    from os import environ
    from sys import stderr, exit

    udunitskey='UDUNITS'
    standardnamekey='CF_STANDARD_NAMES'
    # set defaults
    udunits=''
    standardname=STANDARDNAME
    uploader=None
    useFileName="yes"
    badc=None
    coards=None
    # set to environment variables
    if environ.has_key(udunitskey):
        udunits=environ[udunitskey]
    if environ.has_key(standardnamekey):
        standardname=environ[standardnamekey]

    try:
        (opts,args)=getopt(arglist[1:],'bchlnu:s:',['badc','coards','help','uploader','noname','udunits=','cf_standard_names='])
    except GetoptError:
        stderr.write('%s\n'%__doc__)
        exit(1)
    
    for a, v in opts:
        if a in ('-b','--badc'):
            badc="yes"
            continue
        if a in ('-c','--coards'):
            coards="yes"
            continue
        if a in ('-h','--help'):
            print __doc__
            exit(0)
        if a in ('-l','--uploader'):
            uploader="yes"
            continue
        if a in ('-n','--noname'):
            useFileName="no"
            continue
        if a in ('-u','--udunits'):
            udunits=v
            continue
        if a in ('-s','--cf_standard_names'):
            standardname=v
            continue
            
    if len(args) == 0:
        stderr.write('ERROR in command line\n\nusage:\n%s\n'%__doc__)
        exit(2)

    return (badc,coards,uploader,useFileName,standardname.strip(),udunits.strip(),args)


#--------------------------
# Main Program
#--------------------------

if __name__ == '__main__':

    from sys import argv

    (badc,coards,uploader,useFileName,standardName,udunitsDat,files)=getargs(argv)
    
    inst = CFChecker(uploader=uploader, useFileName=useFileName, badc=badc, coards=coards, cfStandardNamesXML=standardName, udunitsDat=udunitsDat)
    for file in files:
        inst.checker(file)

