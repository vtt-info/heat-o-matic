# main.py - a script for making a temperature regulating PID, running using a Raspberry Pi Pico
# First prototype is using an OLED, rotary encoder and a relay switch (linked to heating device of some sort)
# The display relies on drivers made by Peter Hinch [link](https://github.com/peterhinch/micropython-nano-gui)

# Released under the GPL 3.0

# Fonts for Writer (generated using https://github.com/peterhinch/micropython-font-to-py)
import gui.fonts.freesans20 as freesans20
import gui.fonts.quantico40 as quantico40
from gui.core.writer import CWriter
from gui.core.colors import RED, BLUE, GREEN
from gui.core.nanogui import refresh
import utime
import machine
from machine import Pin,I2C
from rp2 import PIO, StateMachine, asm_pio
import sys
import math
import gc
import onewire, ds18x20

# Look for thermometer
ds_pin = machine.Pin(22)

ds_sensor = ds18x20.DS18X20(onewire.OneWire(ds_pin))

roms = ds_sensor.scan()

print('Thermometer: ', roms)

# *** Choose your color display driver here ***

# STM specific driver
from drivers.ssd1351.ssd1351 import SSD1351 as SSD

height = 128  # height = 128 # 1.5 inch 128*128 display

pdc = machine.Pin(20, machine.Pin.OUT, value=0)
pcs = machine.Pin(17, machine.Pin.OUT, value=1)
prst = machine.Pin(21, machine.Pin.OUT, value=1)
spi = machine.SPI(0,
                  baudrate=10000000,
                  polarity=1,
                  phase=1,
                  bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=machine.Pin(18),
                  mosi=machine.Pin(19),
                  miso=machine.Pin(16))
gc.collect()  # Precaution before instantiating framebuf
ssd = SSD(spi, pcs, pdc, prst, height)  # Create a display instance

# define encoder pins 

#switch = Pin(4, mode=Pin.IN, pull = Pin.PULL_UP) # inbuilt switch on the rotary encoder, ACTIVE LOW
outA = Pin(2, mode=Pin.IN) # Pin CLK of encoder
outB = Pin(3, mode=Pin.IN) # Pin DT of encoder

# Define relay and LED pins

ledPin = Pin(25, mode = Pin.OUT, value = 0) # Onboard led on GPIO 25


# define global variables
counter = 0   # counter updates when encoder rotates
direction = "" # empty string for registering direction change
outA_last = 0 # registers the last state of outA pin / CLK pin
outA_current = 0 # registers the current state of outA pin / CLK pin

button_last_state = False # initial state of encoder's button 
button_current_state = "" # empty string ---> current state of button

# Read the last state of CLK pin in the initialisaton phase of the program 
outA_last = outA.value() # lastStateCLK

# interrupt handler function (IRQ) for CLK and DT pins
def encoder(pin):
    # get global variables
    global counter
    global direction
    global outA_last
    global outA_current
    
    # read the value of current state of outA pin / CLK pin
    outA_current = outA.value()
    
    # if current state is not same as the last stare , encoder has rotated
    if outA_current != outA_last:
        # read outB pin/ DT pin
        # if DT value is not equal to CLK value
        # rotation is clockwise [or Counterclockwise ---> sensor dependent]
        if outB.value() != outA_current:
            counter += .05
        else:
            counter -= .05
        
        # print the data on screen
        #print("Counter : ", counter, "     |   Direction : ",direction)
        #print("\n")
    
    # update the last state of outA pin / CLK pin with the current state
    outA_last = outA_current
    counter=min(90,counter)
    counter=max(45,counter)
    return(counter)
    

# interrupt handler function (IRQ) for SW (switch) pin
def button(pin):
    # get global variable
    global button_last_state
    global button_current_state
    global stack
    if button_current_state != button_last_state:
        print('BUTTON')
        utime.sleep(.1)
        
        button_last_state = button_current_state
    return

def displaynum(num,temperature):
    #This needs to be fast for nice responsive increments
    #100 increments?
    delta=num-temperature
    text=GREEN
    if abs(delta)>.3:
        text=RED
    wri = CWriter(ssd,quantico40, fgcolor=text,bgcolor=0)
    CWriter.set_textpos(ssd, 25,0)  # verbose = False to suppress console output
    wri.printstring(str("{:.1f}".format(num))+" ")
    wrimem = CWriter(ssd,freesans20, fgcolor=255,bgcolor=0)
    CWriter.set_textpos(ssd, 75,0)  
    wrimem.printstring('actual: '+str("{:.1f}".format(temperature))+"   ")
    CWriter.set_textpos(ssd, 95,0)  
    wrimem.printstring('delta:   '+str("{:.1f}".format(delta))+"   ")
    
    ssd.show()
    return

def newsetpoint(offset):
    print('offset:',float(offset))
    # This is where the temperature needs to go
    return

# Attach interrupt to Pins
""" If you need to write a program which triggers an interrupt whenever
    a pin changes, without caring whether it’s rising or falling,
    you can combine the two triggers using a pipe or
    a vertical bar symbol ( | ) . Logical AND """

# attach interrupt to the outA pin ( CLK pin of encoder module )
outA.irq(trigger = Pin.IRQ_RISING | Pin.IRQ_FALLING,
              handler = encoder)

# attach interrupt to the outB pin ( DT pin of encoder module )
outB.irq(trigger = Pin.IRQ_RISING | Pin.IRQ_FALLING ,
              handler = encoder)

# attach interrupt to the switch pin ( SW pin of encoder module )
#switch.irq(trigger = Pin.IRQ_FALLING,
#           handler = button)


# Main Logic
pin=0
counter= 54.5
integral = 0
lastupdate = utime.time()  
refresh(ssd, True)  # Initialise and clear display.

lasterror = 0
# The Tweakable values that will help tune for our use case
checkin = 5
Kp=30.
Ki=0.1
Kd=2
output=100
offstate=False
while True:
    try:
        counter=encoder(pin)
        ds_sensor.convert_temp()
        temp = ds_sensor.read_temp(roms[0])
        displaynum(counter,float(temp))
        button_last_state = False # reset button last state to false again ,
# totally optional and application dependent,
                              # can also be done from other subroutines
                              # or from the main loop
        now = utime.time()
        dt= now-lastupdate
        if output<100 and offstate == False and dt > checkin * round(output)/100 :
            relaypin = Pin(15, mode = Pin.OUT, value =0 )
            offstate= True
            utime.sleep(.1)
        if dt > checkin:
            error=counter-temp
            integral = integral + dt * error
            derivative = (error - lasterror)/dt
            lastupdate = now
            lasterror = error
            output = Kp * error + Ki * integral + Kd * derivative
            output = max(min(100, n), 0) # Clamp output between 0 and 100
            print(output)
            if output>20.:  # If output is more than 20 percent, turn on the heater. Otherwise don't turn it on at all
                relaypin = Pin(15, mode = Pin.OUT, value =1 )
                offstate = False
            else:
                relaypin = Pin(15, mode = Pin.OUT, value =0 )
                offstate = True
            utime.sleep(.1)
    except:
        print('error encountered')
        utime.sleep(checkin)
            
        



