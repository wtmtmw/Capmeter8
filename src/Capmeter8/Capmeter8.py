from PyQt6 import QtWidgets, uic, QtCore
# from pyqtgraph import PlotWidget, plot #for packaging only if loading .ui directly? need to test...
# import pyqtgraph as pg
import sys
import pyqtgraph as pg
from pathlib import Path
import numpy as np
from random import randint
from daqx.util import createDevice
import traceback

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
        
        self.daqdefault = self.kwarg2var(daqid = 0,
                                  aiSR = 100000, #in Hz
                                  aoSR = 100000, #in Hz
                                  aoExtConvert = 20, #in mV/V. For ao_1, not ao_0
                                  )

        self.disp = self.kwarg2var(dispindex = [1,3,5], # 1-based
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
        self.menuindex = [0,0,0,0] # menuID,up aidata,middle aidata,bottom aidata], modified in @MenuSwitcher
        self.limsetindex = [self.AxesSwitch.currentIndex(),True,True,True]; #[axis #,Auto,Auto,Auto]
        self.Auto_axes.setChecked(self.limsetindex[self.limsetindex[0]+1])

        self.plot0 = self.iniAxes(self.axes1,'r')
        self.plot1 = self.iniAxes(self.axes2,'b')
        self.plot2 = self.iniAxes(self.axes3,'r')

        self.labelindex = [] #[dispindex,time,data,'string']
        self.slider1.setMaximum(self.disp.slider1range)
        self.text_slider1.setText(str(self.slider1.value()))
        self.slider2.setMaximum(self.disp.slider2range)
        self.text_slider2.setText(str(self.slider2.value()))
        #TODO - implement the followings
        # handles.fswitch = get(handles.FilterSwitch,'Value')-1;
        # handles.shiftvalue = str2double(get(handles.Phase_Shift,'String')); %offline phase-shift value, in degree
        # handles.shiftswitch = -1; %0:Csqa, 1:Gs qa, -1:G and C for cross correlation
        # handles.Stdfactor = []; %convert volt to fF

        #TODO - other display-related settings

        '''
        List of DAQ-related variables
        '''
        self.disptimer = QtCore.QTimer() #replacing disptimer Fcn for updateing plots
        self.disptimer.setInterval(1000) #in ms
        #TODO - self.rSR = str2double(get(handles.RecordSampleRate,'String'));
        self.rSR = 100
        self.aidata = []
        self.aidata2 = [] # Kseal adjusted data
        self.aodata = []
        self.aitime = []
        self.PSDofSQA = []
        self.Pulsedata = [] # AO1 output array, has been converted to actual Vcmd
        self.Pulselog = []
        #self.rxr = []; %fragments of real-time raw data
        #TODO - self.algorism = get(self.Cm,'Value'); %1:PSD;2:I-SQA;3:Q-SQA
        #TODO - self.autofp = get(self.Auto_FP,'Value'); %for @SqAlgo
        self.autofreq = 0 #for @SqAlgo
        self.autorange = 0 #for @SqAlgo
        #TODO - self.PSDfreq = str2double(get(self.PSD_freq,'String')); 
        self.PSDamp = [] #make it empty in order to enter the 'if' codes in @Set_PSD_Callback
        #TODO - self.PSDphase = str2double(get(self.PSD_phase,'String')); %degree
        self.PSDlog = [] #[time,kHz,mV,degree]
        #TODO - self.PSDwaveindex = get(self.PSD_waveindex,'Value'); %1 for sine wave, 0 for square/triangular wave
        #self.triggervalue = 1; %for v2; fixed 1 volt trigger value
        self.P1 = []
        self.P2 = [] #P1 and P2 are used in @AutoPhase
        self.PSDref = []
        self.PSD90 = []
        #TODO - implement the followings
        # self.fcheck(1,1) = get(self.FilterCheck1,'Value');
        # self.fcheck(1,2) = get(self.FilterCheck2,'Value');
        # self.fcheck(1,3) = get(self.FilterCheck3,'Value');
        # self.fcheck(1,4) = get(self.FilterCheck4,'Value');
        # self.fcheck(1,5) = 1; %Ch5 is the access conductance
        # self.fwindow = abs(round(str2double(get(self.filterset2,'String')))); %running average samples, for Ch1 and Ch2

        # self.saveraw = 0; %save raw data or not
        # self.rxrindex = get(self.RXR,'Value'); %export raw data in real time

        #TODO - implement the followings
        # if(strcmpi(get(handles.context_autofreq,'Checked'),'on'))
        #     handles.autofreq = 1;
        # end
        # if(strcmpi(get(handles.context_autorange,'Checked'),'on'))
        #     handles.autorange = 1;
        # end

        # try
        #      h = Cap7Setting(1); %the numer of 1 informs Cap7Setting to load setting
        #     if ishandle(h)
        #         uiwait(h); %must have uiwait here or nidaqid won't be updated when Cap7Var is absent
        #     end
        #     %assignin('base','output',Settings);
        #     %CapmeterSetting(); %removed, TW141023
        # catch ME_setting
        #     disp('Fail to load settings; default values are used');
        #     guidata(gcf,handles);
        #     assignin('base','ME_setting',ME_setting);
        #     gatherDAQinfo(gcf);
        # end

        #%%
        '''
        Set up AO and AI
        '''
        # create device and AO
        try:
            self.daq = createDevice('mcc',self.daqdefault.daqid)
            self.daq.config_ao(0,1)
            self.daq.ao.endMode = 'hold'
            self.daq.ao.sampleRate = self.daqdefault.aoSR
            self.daq.ao.putvalue([0,0])
        except:
            print('AO error in OpeningFcn')
            self.reader = True
            traceback.print_exc()

        # setup AI
        try:
            self.daq.config_ai(0,1)
            self.daq.ai.trigType = 'digital-positive-edge'
            self.daq.ai.iscontinuous = True
            self.daq.ai.grounding = 'single-ended'
            self.daq.ai.sampleRate = self.daqdefault.aiSR
        except:
            print('AI error in OpeningFcn')
            self.reader = True
        finally:
            self.daq.ai.samplesPerTrig = int(((1/self.rSR)-0.001)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
        
        self.slider1v2p = round(self.slider1.value()*self.disp.slider1range*self.rSR) #for @update_plot, @slider1_Callback
        self.slider2v2p = round(self.slider2.value()*self.disp.slider2range*self.rSR) #for @update_plot, @slider2_Callback
        #TODO - handles.filterv2p = round((str2double(get(handles.filterset,'String'))/1000)*Cap7_state.daq.aiSR); %points to be averaged
        
        self.SpmCount = self.daq.ai.samplesPerTrig*round(self.rSR*0.5) # process data every 0.5 sec
        self.databuffer = np.zeros((2,self.SpmCount)) # pre-allocate memory, for @process_data
        self.timebuffer = np.zeros(self.SpmCount) # pre-allocate memory, for @process_data
        #TODO AI/AO callbacks



        #%% 
        '''
        Connect signals and slots
        '''
        self.disptimer.timeout.connect(self.update_plot)
        self.Start_Stop.clicked.connect(self.Start_Stop_Callback)
        self.uplimdown2.clicked.connect(self.push_ylimAdj)
        self.uplimdown025.clicked.connect(self.push_ylimAdj)
        #TODO - other GUI components
    
    '''
    Function and class definition
    '''
    #%% Utility -------------------------------------------------------
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
        index = int(axes.objectName()[-1]) # index to the axis
        if not self.limsetindex[index]: # if not auto axis
            self.ylim(axes,(-1,1))
        return h
    
    def xlim(self,axes,lim):
        # lim: tuple
        axes.setRange(xRange=lim)

    def ylim(self,axes,lim):
        # lim: tuple
        axes.setRange(yRange=lim)
    
    def pseudoDataGenerator(self,Nsp):
        return [randint(20, 40) for _ in range(Nsp)]

    def update_plot(self):
        #TODO
        XData = list(range(1000))
        YData1 = self.pseudoDataGenerator(len(XData))
        YData2 = self.pseudoDataGenerator(len(XData))
        self.plot1.setData(XData,YData1)
        self.plot2.setData(XData,YData2)
    
    #%% Callbacks -------------------------------------------------------
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

    def push_ylimAdj(self):
        pass
    

#%% -------------------------------------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
