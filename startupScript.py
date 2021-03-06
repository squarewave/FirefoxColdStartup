import os
import subprocess
import pynput
import time
import psutil
import fnmatch
import shutil
import random
import traceback
import ctypes, sys
import winreg
from shutil import move
from pathlib import Path
from datetime import datetime
from pynput.keyboard import Key, Controller
from zipfile import ZipFile
import win32com.shell.shell as win32shell 
import urllib.request
from subprocess import call
from mozprofile import FirefoxProfile, Preferences
from mozrunner import FirefoxRunner

# IMPORTANT NOTE: 
# This script disables UAC prompts, which can leave the system in a vulnerable 
# position. After using the script, you sould re-enable it via the EnableLUA
# registry setting.

# BEFORE RUNNING SCRIPT:
# 1. Ensure Firefox is not in use
# 2. Replace URLs for all builds
# 3. Ensure openProcmon and saveProcmon scripts are in the same directory
#	 as the procmon executable.
# 4. Choose the correct procmon executable in batch files - Procmon.exe or Procmon64.exe
# 5. Ensure your ProcessMonitor installation is located under ~/Documents
# 6. Ensure preferences.js is in home directory

# AFTER RUNNING SCRIPT:
# Re-enable UAC prompts. 

class Build:
	def __init__(self, label, buildLink):
		self.label = label
		self.buildLink = buildLink

# TODO: Edit this list to include labels and links for builds
buildList = [
	Build("control", "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/QZejzYl1TVmmBv8ABXzzAg/runs/0/artifacts/public/build/target.zip"),
	Build("mod_prefetch", "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/CLxX1dPORFKMmGa20KmHvg/runs/0/artifacts/public/build/target.zip"),
]

keyboard = Controller()

# Paths to executables and batch files
home = str(Path.home())
firefox = home + '\\Downloads\\targetUnzip\\firefox\\firefox.exe'
testProfile = home + '\\testprofile'
procmonFolder = home + '\\Documents\\ProcessMonitor'
openProcmonBatch = procmonFolder + '\\openProcmon.bat'
saveProcmonBatch = procmonFolder + '\\saveProcmon.bat'
logPML = procmonFolder + '\\log.pml'
preferences = home + '\\preferences.js'

isFirstRun = False

# Disable UAC prompt to run procmon
def disable_UAC():
    command1 = 'reg delete HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v EnableLUA'
    win32shell.ShellExecuteEx(lpVerb='runas', lpFile='cmd.exe', lpParameters='/c ' + command1)
    command2 = 'reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v EnableLUA /t REG_DWORD /d 0 /f'
    win32shell.ShellExecuteEx(lpVerb='runas', lpFile='cmd.exe', lpParameters='/c ' + command2)

def run_firefox():
	subprocess.Popen([firefox, "-profile", testProfile])

# Create a folder to place all profiles, procmon logs, and disk files into
pathToExperimentFolder = home + '\\Experiment'
# BuildType.txt will indicate if the last run was a control or test build
buildTypeFilePath = pathToExperimentFolder + '\\BuildType.txt'
useRandomBuildPath = pathToExperimentFolder + '\\UseRandomBuild'

# This is not generally advisable, but this will ensure that our script
# doesn't just get hung overnight.
def restart_excepthook(etype, value, tb):
	excString = ''.join(traceback.format_exception(etype, value, tb))
	print(excString)	
	# Append errors to an Errors.txt file so that we can go back and look through them after,
	# say, running the script overnight.
	with open(pathToExperimentFolder + '\\Errors.txt', "a+") as errorFile:
		errorFile.write("##### BEGIN ERROR ####\n")
		errorFile.write(str(datetime.now()) + "\n")
		errorFile.write(excString)
		errorFile.write("#####  END ERROR  ####\n\n")

	# Remove the BuildType.txt file, so the script starts over with a fresh slate.
	# We will however continue to hold on to our results.
	try:
		os.remove(buildTypeFilePath)
	except FileNotFoundError:
		pass

	# Give two minutes for the script runner to maybe look over and notice that the script is
	# in an error state, then just try to restart and continue as usual.
	print("Restarting system in two minutes due to error")
	time.sleep(120)
	os.system("shutdown /r /t 1")


sys.excepthook = restart_excepthook

try:
	os.mkdir(pathToExperimentFolder)
	print ("Successfully created the diretory %s " % pathToExperimentFolder)
except OSError:
	print ("Creation of the directory %s failed because it already exists" % pathToExperimentFolder)

if not os.path.exists(buildTypeFilePath):
	isFirstRun = True

if os.path.exists(useRandomBuildPath):
	useRandomBuild = True
	os.remove(useRandomBuildPath)
else:
	useRandomBuild = False
	open(useRandomBuildPath, "w+").close()

cohort = None

if isFirstRun:
	# Create our file that holds the last build we ran
	print("First run - create BuildType.txt")
	with open(buildTypeFilePath, "w+") as fin:
		pass

	# Disable UAC prompt
	print("Disable UAC prompt")	
	disable_UAC()
	time.sleep(2)
else:
	# Read BuildType file contents to see if it was test or control build 
	# and get the path to the profile.
	with open(buildTypeFilePath, "rt") as fin:
		cohort = fin.read()

	# Start procmon
	print("Start procmon")
	subprocess.call(openProcmonBatch)
	time.sleep(3)

	# Launch the profile
	print("Launching firefox instance that will be profiled")
	run_firefox()

	# Wait for it to settle 
	time.sleep(80)

	# Save Procmon log
	print("Save procmon log and diskify file")
	subprocess.call(saveProcmonBatch)
	
	# Quit Firefox
	print("Quit Firefox")
	with keyboard.pressed(Key.alt):
		keyboard.press(Key.f4)

	time.sleep(30)

	# Delete the build
	print("Delete the build")
	shutil.rmtree(home + '\\Downloads\\targetUnzip')

	# Find the most recent profile written to and grab the most
	# recent "main" ping from the profile
	print("Find recent profile")
	max_mtime = 0
	for dirname,subdirs,files in os.walk(testProfile):
		for fname in files:
			if 'main' in fname:
				full_path = os.path.join(dirname, fname)
				mtime = os.stat(full_path).st_mtime
				if mtime > max_mtime:
					max_mtime = mtime
					max_dir = dirname
					max_file = fname

	# Copy that file into our new experiment directory
	print("Copy profile into experiment directory")
	profileFile = max_dir + "\\" + max_file
	shutil.copy(profileFile, pathToExperimentFolder)

	# Move Procmon log and diskify file into experiment directory.
	print("Move procmon log and diskify file into experiment directory")
	logFile = home + '\\Documents\\ProcessMonitor\\log.csv'
	diskifyFile = home + '\\Documents\\ProcessMonitor\\out.diskify'
	shutil.move(logFile, pathToExperimentFolder)
	shutil.move(diskifyFile, pathToExperimentFolder)
	copiedProfileFile = pathToExperimentFolder + "\\" + max_file 
	copiedProcmonFile = pathToExperimentFolder + "\\log.csv"
	copiedDiskifyFile = pathToExperimentFolder + "\\out.diskify"

	print("Rename files")
	renamedProfileFile = pathToExperimentFolder + "\\" + cohort + "_" + max_file
	renamedProcmonFile = pathToExperimentFolder + "\\" + "procmon_" + os.path.splitext(os.path.basename(renamedProfileFile))[0] + ".csv"
	renamedDiskifyFile = pathToExperimentFolder + "\\" + "diskify_" + os.path.splitext(os.path.basename(renamedProfileFile))[0] + ".diskify"
	os.rename(copiedProfileFile, renamedProfileFile)
	os.rename(copiedProcmonFile, renamedProcmonFile)
	os.rename(copiedDiskifyFile, renamedDiskifyFile)

	# Delete log.pml file
	print("Delete log.pml")
	os.remove(logPML)

# Randomly select what type of build we are going to profile
if useRandomBuild or not cohort:
	testBuild = random.choice(buildList)
else:
	testBuild = next(build for build in buildList if build.label != cohort)

print("Append correct information to BuildType.txt")
cohort = testBuild.label

# Write what type of build it is to the build file
print("Write information to BuildType.txt")
with open(buildTypeFilePath, "wt") as fin:
	fin.write(cohort)

# Download a build from task cluster 
print("Download build from task cluster")
downloadedPath = home + '\\Downloads\\target.zip'
urllib.request.urlretrieve(testBuild.buildLink, downloadedPath)

print("Delete the profile")
try:
	shutil.rmtree(testProfile)
except FileNotFoundError:
	pass

# Unzip the files within target directory
print("Unzip build files")
with ZipFile(downloadedPath, 'r') as zipObj:
	zipObj.extractall(home + '\\Downloads\\targetUnzip')
os.remove(downloadedPath)

# Copy the prefs file into the build
prefLocation = home + '\\Downloads\\targetUnzip\\firefox\\browser\\defaults\\preferences\\preferences.js'
# Create defaults\preferences directories to place preferences.js into
try:
	os.mkdir(home + '\\Downloads\\targetUnzip\\firefox\\browser\\defaults')
except OSError:
	pass
try:
	os.mkdir(home + '\\Downloads\\targetUnzip\\firefox\\browser\\defaults\\preferences')
except OSError:
	pass

shutil.copy(preferences, prefLocation)


# Run build, close it, run it, close it
buildStarts = 2
while buildStarts > 0:
	print("Run build")
	run_firefox()

	# Wait for it to settle
	time.sleep(60)
	
	# Quit the application, one is sufficient because of preferences^
	print("Close the build")
	with keyboard.pressed(Key.alt):
		keyboard.press(Key.f4)
	buildStarts -= 1
	time.sleep(30)

# Restart
print("Restart system")
os.system("shutdown /r /t 1")