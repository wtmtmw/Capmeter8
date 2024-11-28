from PyQt6 import QtWidgets, uic, QtCore
# from pyqtgraph import PlotWidget, plot #for packaging only if loading .ui directly? need to test...
# import pyqtgraph as pg
import sys
import pyqtgraph as pg
from pathlib import Path
from random import randint
from daqx.util import createDevice

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        '''
        Set up variables
        '''
        self.appdir = Path(__file__).parent
        
        self.pulse = self.kwarg2var(JustDone = 0,  #blank C,G,Ra and assign data used in @process_data and @resume
                                   pulsing = False,
                                   notPartOfPulseTriggers = 0,  #TW161218, number of triggers in the DAQ engine which are not part of the pulse. Calculated in Pulse_Callback
                                   data = None)
        
        self.daq = self.kwarg2var(daqid = None,
                                  aiSR = 100000, #in Hz
                                  aoSR = 100000, #in Hz
                                  aoExtConvert = 20, #in mV/V. For ao_1, not ao_0
                                  )

        self.disp = self.kwarg2var(dispindex = [1,3,5],
                                   slider1range = 120,
                                   slider2range = 50)
        
        self.gh = self.kwarg2var(notePad = None) #TODO - Cap7_gh has not been implemented

        self.current_folder = Path.cwd()
        self.changed = False #if the note etc. have been changed;
        self.applyKseal = False #show Kseal adjusted data or not
        self.reader = False

        #TODO - Button groups
        #TODO - Filter group
        #TODO - Pulse group
        #TODO - KeyPress group
        #TODO - Reader group
        #TODO - set button availability

        '''
        Load and setup the UI Page
        '''
        uic.loadUi(Path(self.appdir,'ui_Cap8MainWindow.ui'), self)
        self.plot1 = self.iniAxes(self.axes1,'r')
        self.plot2 = self.iniAxes(self.axes2,'b')
        self.plot3 = self.iniAxes(self.axes3,'r')
        #TODO - display-related settings, context menu etc.

        '''
        List of DAQ-related variables
        '''

        self.disptimer = QtCore.QTimer() #replacing disptimer Fcn for updateing plots
        self.disptimer.setInterval(1000) #in ms
        #TODO

        '''
        Connect signals and slots
        '''
        self.disptimer.timeout.connect(self.update_plot)
        self.Start_Stop.clicked.connect(self.Start_Stop_Callback)
        #TODO - other GUI components
    
    '''
    Function and class definition
    '''
    class kwarg2var:
        #container class; used for mimicing the struct data type
        def __init__(self, **kwarg):
            #print(type(kwarg)) #dict
            for key, value in kwarg.items():
                setattr(self, key, value)

    def iniAxes(self,axes,color):
        #initializ the display axes
        h = axes.plot([0],[0],pen=pg.mkPen(width=2, color=color))
        axes.setBackground('w')
        return h

    def Start_Stop_Callback(self):
        #TODO
        if self.Start_Stop.isChecked(): #start
            self.Start_Stop.setText('Started')
            self.Start_Stop.setStyleSheet('color:green')
            self.disptimer.start()
        else: #stop
            self.Start_Stop.setText('Stopped')
            self.Start_Stop.setStyleSheet('color:red')
            self.disptimer.stop()
    
    #%% -------------------------------------------------------
    def pseudoDataGenerator(self,Nsp):
        return [randint(20, 40) for _ in range(Nsp)]

    def update_plot(self):
        #TODO
        XData = list(range(1000))
        YData1 = self.pseudoDataGenerator(len(XData))
        YData2 = self.pseudoDataGenerator(len(XData))
        self.plot1.setData(XData,YData1)
        self.plot2.setData(XData,YData2)

#%% -------------------------------------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
