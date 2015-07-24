import argparse
import glob
import numpy
import os
import subprocess
import sys

from setuptools import setup, find_packages, Extension

"""
This file builds and installs the NuPIC Core bindings
"""

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
DARWIN_PLATFORM = "darwin"
LINUX_PLATFORM = "linux"
UNIX_PLATFORMS = [LINUX_PLATFORM, DARWIN_PLATFORM]
WINDOWS_PLATFORMS = ["windows"]



def fixPath(path):
  """
  Ensures paths are correct for linux and windows
  """
  path = os.path.abspath(os.path.expanduser(path))
  if path.startswith("\\"):
    return "C:" + path

  return path



def findRequirements():
  """
  Read the requirements.txt file and parse into requirements for setup's
  install_requirements option.
  """
  requirementsPath = os.path.normpath(fixPath(SRC_DIR + "/../external/common/requirements.txt"))
  return [
    line.strip()
    for line in open(requirementsPath).readlines()
    if not line.startswith("#")
  ]



def printOptions(optionsDesc):
  """
  Print command line options.
  """

  print "Options:\n"

  for option in optionsDesc:
    optionUsage = "--" + option[0]
    if option[1] != "":
      optionUsage += "=[" + option[1] + "]"

    optionDesc = option[2]
    print "    " + optionUsage.ljust(30) + " = " + optionDesc



def getCommandLineOptions():

  # optionDesc = [name, value, description]
  optionsDesc = []
  optionsDesc.append(
    ["nupic-core-dir",
     "dir",
     "(optional) Absolute path to nupic.core binary release directory"]
  )

  optionsDesc.append(
    ["visual-studio-version",
     "value",
     "(optional) Version of visual studio if windows (i.e. Microsoft Visual Studio *.*)"]
  )
  optionsDesc.append(
    ["skip-compare-versions",
     "",
     "(optional) Skip nupic.core version comparison"]
  )
  optionsDesc.append(
    ["optimizations-native",
    "value",
    "(optional) enable aggressive compiler optimizations"]
  )
  optionsDesc.append(
    ["optimizations-lto",
    "value",
    "(optional) enable link-time optimizations (LTO); currently only for gcc and linker ld.gold"]
  )
  optionsDesc.append(
    ["debug",
    "value",
    "(optional) compile in mode suitable for debugging; overrides any optimizations"]
  )

  # Read command line options looking for extra options
  # For example, an user could type:
  #   python setup.py install --nupic-core-dir="path/to/release"
  # which will set the nupic.core release dir
  optionsValues = dict()
  for arg in sys.argv[:]:
    optionFound = False
    for option in optionsDesc:
      name = option[0]
      if "--" + name in arg:
        value = None
        hasValue = (option[1] != "")
        if hasValue:
          value = arg.partition("=")[2]

        optionsValues[name] = value
        sys.argv.remove(arg)
        optionFound = True
        break

    if not optionFound:
      if ("--help-nupic" in arg):
        printOptions(optionsDesc)
        sys.exit()

  return optionsValues



def getCommandLineOption(name, options):
  if name is None or options is None:
    return False
  if name in options:
    return options[name]



def getPlatformInfo():
  """
  Identify platform
  """
  if "linux" in sys.platform:
    platform = "linux"
  elif "darwin" in sys.platform:
    platform = "darwin"
  elif sys.platform.startswith("win"):
    platform = "windows"
  else:
    raise Exception("Platform '%s' is unsupported!" % sys.platform)

  if sys.maxsize > 2**32:
    bitness = "64"
  else:
    bitness = "32"

  return platform, bitness



def generateSwigWrap(swigExecutable, swigFlags, interfaceFile,
  language="python"):
  """
  Generate C++ code from the specified SWIG interface file.
  """
  wrap = interfaceFile.replace(".i", "_wrap.cxx")

  cmd = swigExecutable + " -c++ -{} ".format(language)
  for flag in swigFlags:
    cmd += flag + " "
  cmd += interfaceFile
  print cmd
  proc = subprocess.Popen(cmd, shell=True)
  proc.wait()

  return wrap



def getLibPrefix(platform):
  """
  Returns the default system prefix of a compiled library.
  """
  if platform in UNIX_PLATFORMS:
    return "lib"
  elif platform in WINDOWS_PLATFORMS:
    return ""



def getStaticLibExtension(platform):
  """
  Returns the default system extension of a compiled static library.
  """
  if platform in UNIX_PLATFORMS:
    return ".a"
  elif platform in WINDOWS_PLATFORMS:
    return ".lib"



def getExtensionModules(nupicCoreReleaseDir, platform, bitness, cmdOptions):
  #
  # Gives the version of Python necessary to get installation directories
  # for use with pythonVersion, etc.
  #
  if sys.version_info < (2, 7):
    raise Exception("Fatal Error: Python 2.7 or later is required.")

  pythonVersion = str(sys.version_info[0]) + '.' + str(sys.version_info[1])

  #
  # Find out where system installation of python is.
  #
  pythonPrefix = sys.prefix
  pythonPrefix = pythonPrefix.replace("\\", "/")
  pythonIncludeDir = fixPath(pythonPrefix + "/include/python" + pythonVersion)

  #
  # Finds out version of Numpy and headers' path.
  #
  numpyIncludeDir = numpy.get_include()
  numpyIncludeDir = numpyIncludeDir.replace("\\", "/")

  commonDefines = [
    ("NUPIC2", None),
    ("NTA_OS_" + platform.upper(), None),
    ("NTA_ARCH_" + bitness, None),
    ("NTA_PYTHON_SUPPORT", pythonVersion),
    ("NTA_INTERNAL", None),
    ("NTA_ASSERTIONS_ON", None),
    ("NTA_ASM", None),
    ("HAVE_CONFIG_H", None),
    ("BOOST_NO_WREGEX", None)]

  commonIncludeDirs = [
    os.path.normpath(fixPath(SRC_DIR + "/../external/" + platform + bitness + "/include")),
    os.path.normpath(fixPath(SRC_DIR + "/../external/common/include")),
    fixPath(nupicCoreReleaseDir + "/include"),
    pythonIncludeDir,
    SRC_DIR,
    numpyIncludeDir]

  commonCompileFlags = [
    # Adhere to c++11 spec
    "-std=c++11",
    # Generate 32 or 64 bit code
    "-m" + bitness,
    # `position independent code`, required for shared libraries
    "-fPIC",
    "-fvisibility=hidden",
    "-Wall",
    # optimization flags (generic builds used for binary distribution)
    "-mtune=generic",
    "-O2",
  ]
  if platform == "darwin":
    commonCompileFlags.append("-stdlib=libc++")

  if platform != "windows":
    commonCompileFlags.append("-Wextra")
    commonCompileFlags.append("-Wreturn-type")
    commonCompileFlags.append("-Wunused")
    commonCompileFlags.append("-Wno-unused-parameter")

  commonLinkFlags = [
    "-m" + bitness,
    "-fPIC",
    "-L" + fixPath(nupicCoreReleaseDir + "/lib"),
    # for Cap'n'Proto serialization
    "-lkj",
    "-lcapnp",
    "-lcapnpc",
    # optimization (safe defaults)
    "-O2",
  ]

  # Optimizations
  if getCommandLineOption("debug", cmdOptions):
    commonCompileFlags.append("-Og")
    commonCompileFlags.append("-g")
    commonLinkFlags.append("-O0")
  else:
    if getCommandLineOption("optimizations-native", cmdOptions):
      commonCompileFlags.append("-march=native")
      commonCompileFlags.append("-O3")
      commonLinkFlags.append("-O3")
    if getCommandLineOption("optimizations-lto", cmdOptions):
      commonCompileFlags.append("-fuse-linker-plugin")
      commonCompileFlags.append("-flto-report")
      commonCompileFlags.append("-fuse-ld=gold")
      commonCompileFlags.append("-flto")
      commonLinkFlags.append("-flto")

  commonLibraries = [
    "dl",
    "python" + pythonVersion,
    "kj",
    "capnp",
    "capnpc"]
  if platform == "linux":
    commonLibraries.extend(["pthread"])

  commonObjects = [
    fixPath(nupicCoreReleaseDir + "/lib/" +
      getLibPrefix(platform) + "nupic_core" + getStaticLibExtension(platform))]

  supportFiles = [
    os.path.relpath(fixPath(nupicCoreReleaseDir + "/include/nupic/py_support/NumpyVector.cpp"), SRC_DIR),
    os.path.relpath(fixPath(nupicCoreReleaseDir + "/include/nupic/py_support/PyArray.cpp"), SRC_DIR),
    os.path.relpath(fixPath(nupicCoreReleaseDir + "/include/nupic/py_support/PyHelpers.cpp"), SRC_DIR),
    os.path.relpath(fixPath(nupicCoreReleaseDir + "/include/nupic/py_support/PythonStream.cpp"), SRC_DIR)]

  # To find stdlib.h
  #if platform == "windows":
  #  vsVersion = getCommandLineOption('visual-studio-version', cmdOptions)
  #  if vsVersion is None:
  #    raise Exception("Must provide visual studio version if using windows")

  #  stdlib = os.path.relpath(fixPath('C:\\Program Files (x86)\\' + vsVersion + '\\VC\\include\\stdlib.h'), SRC_DIR)
  #  supportFiles.append(stdlib)

  extensions = []

  #
  # SWIG
  #
  swigDir = os.path.normpath(fixPath(SRC_DIR + "/../external/common/share/swig/3.0.2"))
  swigExecutable = (
    os.path.normpath(fixPath(SRC_DIR + "/../external/" + platform + bitness + "/bin/swig"))
  )

  # SWIG options from:
  # https://github.com/swig/swig/blob/master/Source/Modules/python.cxx#L111
  swigFlags = [
    "-features",
    "autodoc=0,directors=0",
    "-noproxyimport",
    "-keyword",
    "-modern",
    "-modernargs",
    "-noproxydel",
    "-fvirtual",
    "-fastunpack",
    "-nofastproxy",
    "-fastquery",
    "-outputtuple",
    "-castmode",
    "-nosafecstrings",
    "-w402", #TODO silence warnings
    "-w503",
    "-w511",
    "-w302",
    "-w362",
    "-w312",
    "-w389",
    "-DSWIG_PYTHON_LEGACY_BOOL",
    "-I" + swigDir + "/python",
    "-I" + swigDir]
  for define in commonDefines:
    item = "-D" + define[0]
    if define[1]:
      item += "=" + define[1]
    swigFlags.append(item)
  for includeDir in commonIncludeDirs:
    item = "-I" + includeDir
    swigFlags.append(item)

  wrapAlgorithms = generateSwigWrap(swigExecutable,
                                    swigFlags,
                                    os.path.relpath(fixPath("nupic/bindings/algorithms.i"), SRC_DIR))
  libModuleAlgorithms = Extension(
    "nupic.bindings._algorithms",
    extra_compile_args=commonCompileFlags,
    define_macros=commonDefines,
    extra_link_args=commonLinkFlags,
    include_dirs=commonIncludeDirs,
    libraries=commonLibraries,
    sources=supportFiles + [wrapAlgorithms],
    extra_objects=commonObjects)
  extensions.append(libModuleAlgorithms)

  wrapEngineInternal = generateSwigWrap(swigExecutable,
                                        swigFlags,
                                        os.path.relpath(fixPath("nupic/bindings/engine_internal.i"), SRC_DIR))
  libModuleEngineInternal = Extension(
    "nupic.bindings._engine_internal",
    extra_compile_args=commonCompileFlags,
    define_macros=commonDefines,
    extra_link_args=commonLinkFlags,
    include_dirs=commonIncludeDirs,
    libraries=commonLibraries,
    sources=[wrapEngineInternal],
    extra_objects=commonObjects)
  extensions.append(libModuleEngineInternal)

  wrapMath = generateSwigWrap(swigExecutable,
                              swigFlags,
                              os.path.relpath(fixPath("nupic/bindings/math.i"), SRC_DIR))
  libModuleMath = Extension(
    "nupic.bindings._math",
    extra_compile_args=commonCompileFlags,
    define_macros=commonDefines,
    extra_link_args=commonLinkFlags,
    include_dirs=commonIncludeDirs,
    libraries=commonLibraries,
    sources=supportFiles + [wrapMath, os.path.relpath(fixPath("nupic/bindings/PySparseTensor.cpp"), SRC_DIR)],
    extra_objects=commonObjects)
  extensions.append(libModuleMath)

  return extensions



if __name__ == "__main__":
  options = getCommandLineOptions()
  platform, bitness = getPlatformInfo()

  print "NUMPY VERSION: {}".format(numpy.__version__)

  nupicCoreReleaseDir = getCommandLineOption("nupic-core-dir", options)
  print "Nupic Core Release Directory: {}\n".format(nupicCoreReleaseDir)
  if not os.path.isdir(nupicCoreReleaseDir):
    raise Exception("{} does not exist".format(nupicCoreReleaseDir))

  if platform == DARWIN_PLATFORM and not "ARCHFLAGS" in os.environ:
    raise Exception("To build NuPIC in OS X, you must "
                    "`export ARCHFLAGS=\"-arch x86_64\"`.")

  # Build and setup NuPIC.Core Bindings
  print "Get SWIG C++ extensions"
  extensions = getExtensionModules(nupicCoreReleaseDir, platform, bitness,
    options)

  print "\nSetup SWIG Python module"
  setup(
    name="nupiccore-python",
    ext_modules=extensions,
    version="1.0",
    namespace_packages=["nupic", "nupic.bindings"],
    install_requires=findRequirements(),
    description="Numenta Platform for Intelligent Computing - bindings",
    author="Numenta",
    author_email="help@numenta.org",
    url="https://github.com/numenta/nupic.core",
    classifiers=[
      "Programming Language :: Python",
      "Programming Language :: Python :: 2",
      "License :: OSI Approved :: GNU General Public License (GPL)",
      "Operating System :: MacOS :: MacOS X",
      "Operating System :: POSIX :: Linux",
      # It has to be "5 - Production/Stable" or else pypi rejects it!
      "Development Status :: 5 - Production/Stable",
      "Environment :: Console",
      "Intended Audience :: Science/Research",
      "Topic :: Scientific/Engineering :: Artificial Intelligence"
    ],
    long_description = "Python bindings for nupic core.",
    packages=find_packages())

