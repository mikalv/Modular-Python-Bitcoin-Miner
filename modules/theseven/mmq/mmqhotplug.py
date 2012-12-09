# Modular Python Bitcoin Miner
# Copyright (C) 2011-2012 Michael Sparmann (TheSeven)
#
#     This program is free software; you can redistribute it and/or
#     modify it under the terms of the GNU General Public License
#     as published by the Free Software Foundation; either version 2
#     of the License, or (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Please consider donating to 1PLAPWDejJPJnY2ppYCgtw5ko8G5Q4hPzh if you
# want to support further development of the Modular Python Bitcoin Miner.



###########################################
# ModMiner Quad hotplug controller module #
###########################################



import traceback
from glob import glob
from threading import Condition, Thread
from core.baseworker import BaseWorker
from .mmqworker import MMQWorker



# Worker main class, referenced from __init__.py
class MMQHotplugWorker(BaseWorker):
  
  version = "theseven.mmq hotplug manager v0.1.0"
  default_name = "MMQ hotplug manager"
  can_autodetect = True
  settings = dict(BaseWorker.settings, **{
    "firmware": {"title": "Firmware file location", "type": "string", "position": 1200},
    "scaninterval": {"title": "Bus scan interval", "type": "float", "position": 2200},
    "initialspeed": {"title": "Initial clock frequency", "type": "int", "position": 3000},
    "maximumspeed": {"title": "Maximum clock frequency", "type": "int", "position": 3100},
    "tempwarning": {"title": "Warning temperature", "type": "int", "position": 4000},
    "tempcritical": {"title": "Critical temperature", "type": "int", "position": 4100},
    "invalidwarning": {"title": "Warning invalids", "type": "int", "position": 4200},
    "invalidcritical": {"title": "Critical invalids", "type": "int", "position": 4300},
    "warmupstepshares": {"title": "Shares per warmup step", "type": "int", "position": 4400},
    "speedupthreshold": {"title": "Speedup threshold", "type": "int", "position": 4500},
    "jobinterval": {"title": "Job interval", "type": "float", "position": 5100},
    "pollinterval": {"title": "Poll interval", "type": "float", "position": 5200},
  })
  
  
  @classmethod
  def autodetect(self, core):
    try:
      import serial
      found = False
      for port in glob("/dev/serial/by-id/usb-BTCFPGA_ModMiner_LJRalpha_*"):
        try:
          handle = serial.Serial(port, 115200, serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_ONE, 1, False, False, 5, False, None)
          handle.close()
          found = True
          break
        except: pass
      if found: core.add_worker(self(core))
    except: pass
    
    
  # Constructor, gets passed a reference to the miner core and the saved worker state, if present
  def __init__(self, core, state = None):
    # Initialize bus scanner wakeup event
    self.wakeup = Condition()

    # Let our superclass do some basic initialization and restore the state if neccessary
    super(MMQHotplugWorker, self).__init__(core, state)

    
  # Validate settings, filling them with default values if neccessary.
  # Called from the constructor and after every settings change.
  def apply_settings(self):
    # Let our superclass handle everything that isn't specific to this worker module
    super(MMQHotplugWorker, self).apply_settings()
    if not "firmware" in self.settings or not self.settings.firmware:
      self.settings.firmware = "modules/theseven/mmq/firmware/"
    if not "initialspeed" in self.settings: self.settings.initialspeed = 150
    self.settings.initialspeed = min(max(self.settings.initialspeed, 4), 250)
    if not "maximumspeed" in self.settings: self.settings.maximumspeed = 200
    self.settings.maximumspeed = min(max(self.settings.maximumspeed, 4), 300)
    if not "tempwarning" in self.settings: self.settings.tempwarning = 45
    self.settings.tempwarning = min(max(self.settings.tempwarning, 0), 60)
    if not "tempcritical" in self.settings: self.settings.tempcritical = 55
    self.settings.tempcritical = min(max(self.settings.tempcritical, 0), 80)
    if not "invalidwarning" in self.settings: self.settings.invalidwarning = 2
    self.settings.invalidwarning = min(max(self.settings.invalidwarning, 1), 10)
    if not "invalidcritical" in self.settings: self.settings.invalidcritical = 10
    self.settings.invalidcritical = min(max(self.settings.invalidcritical, 1), 50)
    if not "warmupstepshares" in self.settings: self.settings.warmupstepshares = 5
    self.settings.warmupstepshares = min(max(self.settings.warmupstepshares, 1), 10000)
    if not "speedupthreshold" in self.settings: self.settings.speedupthreshold = 100
    self.settings.speedupthreshold = min(max(self.settings.speedupthreshold, 50), 10000)
    if not "jobinterval" in self.settings or not self.settings.jobinterval: self.settings.jobinterval = 60
    if not "pollinterval" in self.settings or not self.settings.pollinterval: self.settings.pollinterval = 0.1
    if not "scaninterval" in self.settings or not self.settings.scaninterval: self.settings.scaninterval = 10
    # Push our settings down to our children
    fields = ["firmware", "initialspeed", "maximumspeed", "tempwarning", "tempcritical", "invalidwarning",
              "invalidcritical", "warmupstepshares", "speedupthreshold", "jobinterval", "pollinterval"]
    for child in self.children:
      for field in fields: child.settings[field] = self.settings[field]
      child.apply_settings()
    # Rescan the bus immediately to apply the new settings
    with self.wakeup: self.wakeup.notify()
    

  # Reset our state. Called both from the constructor and from self.start().
  def _reset(self):
    # Let our superclass handle everything that isn't specific to this worker module
    super(MMQHotplugWorker, self)._reset()


  # Start up the worker module. This is protected against multiple calls and concurrency by a wrapper.
  def _start(self):
    # Let our superclass handle everything that isn't specific to this worker module
    super(MMQHotplugWorker, self)._start()
    # Initialize child map
    self.childmap = {}
    # Reset the shutdown flag for our threads
    self.shutdown = False
    # Start up the main thread, which handles pushing work to the device.
    self.mainthread = Thread(None, self.main, self.settings.name + "_main")
    self.mainthread.daemon = True
    self.mainthread.start()
  
  
  # Shut down the worker module. This is protected against multiple calls and concurrency by a wrapper.
  def _stop(self):
    # Let our superclass handle everything that isn't specific to this worker module
    super(MMQHotplugWorker, self)._stop()
    # Set the shutdown flag for our threads, making them terminate ASAP.
    self.shutdown = True
    # Trigger the main thread's wakeup flag, to make it actually look at the shutdown flag.
    with self.wakeup: self.wakeup.notify()
    # Wait for the main thread to terminate.
    self.mainthread.join(10)
    # Shut down child workers
    while self.children:
      child = self.children.pop(0)
      try:
        self.core.log(self, "Shutting down worker %s...\n" % (child.settings.name), 800)
        child.stop()
      except Exception as e:
        self.core.log(self, "Could not stop worker %s: %s\n" % (child.settings.name, traceback.format_exc()), 100, "rB")

      
  # Main thread entry point
  # This thread is responsible for scanning for boards and spawning worker modules for them
  def main(self):
    import serial
    number = 0

    # Loop until we are shut down
    while not self.shutdown:

      try:
        boards = {}
        for port in glob("/dev/serial/by-id/usb-BTCFPGA_ModMiner_LJRalpha_*"):
          available = False
          try:
            handle = serial.Serial(port, 115200, serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_ONE, 1, False, False, 5, False, None)
            handle.close()
            available = True
          except: pass
          boards[port] = available

        kill = []
        for port, child in self.childmap.items():
          if not port in boards:
            kill.append((port, child))

        for port, child in kill:
          try:
            self.core.log(self, "Shutting down worker %s...\n" % (child.settings.name), 800)
            child.stop()
          except Exception as e:
            self.core.log(self, "Could not stop worker %s: %s\n" % (child.settings.name, traceback.format_exc()), 100, "rB")
          childstats = child.get_statistics()
          fields = ["ghashes", "jobsaccepted", "jobscanceled", "sharesaccepted", "sharesrejected", "sharesinvalid"]
          for field in fields: self.stats[field] += childstats[field]
          try: self.child.destroy()
          except: pass
          del self.childmap[port]
          try: self.children.remove(child)
          except: pass

        for port, available in boards.items():
          if port in self.childmap or not available: continue
          number += 1
          child = MMQWorker(self.core)
          child.settings.name = "Autodetected MMQ device %d" % number
          child.settings.port = port
          fields = ["firmware", "initialspeed", "maximumspeed", "tempwarning", "tempcritical", "invalidwarning",
                    "invalidcritical", "warmupstepshares", "speedupthreshold", "jobinterval", "pollinterval"]
          for field in fields: child.settings[field] = self.settings[field]
          child.apply_settings()
          self.childmap[port] = child
          self.children.append(child)
          try:
            self.core.log(self, "Starting up worker %s...\n" % (child.settings.name), 800)
            child.start()
          except Exception as e:
            self.core.log(self, "Could not start worker %s: %s\n" % (child.settings.name, traceback.format_exc()), 100, "rB")

      except: self.core.log(self, "Caught exception: %s\n" % traceback.format_exc(), 100, "rB")

      with self.wakeup: self.wakeup.wait(self.settings.scaninterval)
