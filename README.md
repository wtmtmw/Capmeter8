# Capmeter8
- Python implementation of algorithms and software published by [Wang and Hilgemann (2008)](https://doi.org/10.1085/jgp.200709950).

- MATLAB version of the software is provided in the publication above and [here](https://sites.google.com/site/capmeter/home).

- It is still a work in progress. Some buttons are disabled intentionally as the functionalities have not been implemented yet.

## Installation
:warning: Please install the hardware driver before proceeding.

If you have python installed, you may install Capmeter8 using the ``pip`` command.
Executable version ``.exe`` can also be downloaded from the ``dist`` folder and run under a Windows console ``cmd``.
``` python
# install from the main branch
pip install git+https://github.com/wtmtmw/Capmeter8.git 

# install from the development branch
pip install git+https://github.com/wtmtmw/Capmeter8.git@dev
```
## Hardware Configuration
Hardware support is provided by package [daqx](https://github.com/wtmtmw/daqx), which only supports boards from Measurement Computing for now. Support for National Instruments boards will be added in the future.

Capmeter8 is developed using a [USB-1608GX-2AO](https://digilent.com/shop/mcc-usb-1608g-series-high-speed-multifunction-usb-daq-devices/) board from Measurement Computing.
### Wiring
AO0 → AI0 and Trig<br>
AO1 → External command of the patch clamp

AI0 → AO0<br>
AI1 → Current signal from the patch clamp<br>
AI2 → Something else you would like to record (optinal)

### Connecting to a hardware lock-in amplifier
Instead of serving as a software capacitance meter, Capmeter8 can also function as a plain signal recorder. If you choose to record from a hardware [lock-in amplifier](https://www.thinksrs.com/products/sr830.html), please follow the wiring below:

AO0 → Trig<br>
AO1 → External command of the patch clamp (optinal)

AI0 → Lock-in amplifier, Ch2 (Y, capacitance)<br>
AI1 → Lock-in amplifier, Ch1 (X, conductance)<br>
AI2 → Something else you would like to record (optinal)
