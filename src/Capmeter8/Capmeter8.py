from PyQt6 import QtWidgets, uic, QtCore
# from pyqtgraph import PlotWidget, plot #for packaging only if loading .ui directly? need to test...
import sys, traceback, ctypes
import pyqtgraph as pg
from pathlib import Path
import numpy as np
from math import ceil
from time import sleep
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

        self.plot1 = self.iniAxes(self.axes1,'r')
        self.plot2 = self.iniAxes(self.axes2,'b')
        self.plot3 = self.iniAxes(self.axes3,'r')

        self.labelindex = [] #[dispindex,time,data,'string']
        self.slider1.setMaximum(self.disp.slider1range)
        self.text_slider1.setText(f'{self.slider1.value():.0f}')
        self.slider2.setMaximum(self.disp.slider2range)
        self.text_slider2.setText(f'{self.slider2.value():.0f}')
        #TODO - implement the followings
        self.fswitch = self.FilterSwitch.currentIndex()
        self.shiftvalue = float(self.Phase_Shift.text())
        self.shiftswitch = -1 #0:Csqa, 1:Gs qa, -1:G and C for cross correlation
        self.Stdfactor = [] #convert volt to fF

        #TODO - other display-related settings

        '''
        List of DAQ-related variables
        '''
        self.disptimer = QtCore.QTimer() #connected to update_plot()
        self.disptimer.setInterval(1000) #in ms
        self.rSR = abs(float(self.RecordSampleRate.text()))
        self.aidata = [] # M-by-Timepoint matrix, where M is the number of parameters/channels
        self.aidata2 = [] # Kseal adjusted data
        self.aodata = []
        self.aitime = []
        self.PSDofSQA = []
        self.Pulsedata = [] # AO1 output array, has been converted to actual Vcmd
        self.Pulselog = []
        #self.rxr = []; %fragments of real-time raw data
        # Note - self.Cm.currentIndex() - 0:Hardware; 1:PSD; 2:I-SQA; 3:Q-SQA
        self.algorithm = self.Cm.currentIndex()

        self.autofp = self.Auto_FP.isChecked() #for @SqAlgo
        self.autofreq = False #for @SqAlgo
        self.autorange = False #for @SqAlgo
        self.PSDfreq = float(self.PSD_freq.text()) 
        self.PSDamp = [] #make it empty in order to enter the 'if' codes in @Set_PSD_Callback
        self.PSDphase = float(self.PSD_phase.text()) #degree
        self.PSDlog = [] #[[time,kHz,mV,degree,algorithm],...]
        #Remove - self.PSDwaveindex = get(self.PSD_waveindex,'Value'); %1 for sine wave, 0 for square/triangular wave
        self.P1 = []
        self.P2 = [] #P1 and P2 are used in @AutoPhase
        self.PSDref = []
        self.PSD90 = []
        # Note - revamp fcheck structure
        self.fcheck = {'rf0':True, 'rf1':True, 'rf2':True,
                       'mf0':False,'mf1':False,'mf2':False,'mf3':False,'mf4':False}
        for key,value in self.fcheck.items():
            exec(f'self.{key}.setChecked({value})')
        self.fwindow = abs(int(self.filterset2.text())) #samples for the moving filter

        #TODO - implement the followings
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
        Set up C functions
        '''
        self.lib = ctypes.CDLL(str(Path(self.appdir,'caplib.dll')))
        self.lib.Dfilter.restype = None
        self.lib.Dfilter.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self.lib.PSD.restype = None
        self.lib.PSD.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self.lib.SqCF.restype = None
        self.lib.SqCF.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
        self.lib.SqQ.restype = None
        self.lib.SqQ.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
        self.lib.SqWaveCalc.restype = None
        self.lib.SqWaveCalc.argtypes = [ctypes.c_int,ctypes.c_int,ctypes.c_double]
        
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
            self.daq.config_ai(0,2) #Ch0: trigger, used in CapEngine; Ch1: current; Ch2: e.g. Ampero signal
            self.daq.ai.trigType = 'digital-positive-edge'
            self.daq.ai.iscontinuous = True
            self.daq.ai.aqMode = 'background'
            self.daq.ai.grounding = 'single-ended'
            self.daq.ai.sampleRate = self.daqdefault.aiSR
            self.daq.ai.samplesPerTrig = int(((1/self.rSR)*0.9)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
        except:
            print('AI error in OpeningFcn')
            self.reader = True
        finally:
            pass
            #TODO - handle if samplesPerTrig < 1 e.g. rSR = 1000Hz
        
        # the calculation of sliderv2p as it behaves differently in MATLAB and PyQt
        #TODO - remove sliderv2p in future release
        self.slider1v2p = round(self.slider1.value()*self.rSR) #for @update_plot, @slider1_Callback
        self.slider2v2p = round(self.slider2.value()*self.rSR) #for @update_plot, @slider2_Callback
        self.filterv2p = round((float(self.filterset.text())/1000)*self.daq.ai.sampleRate) #points to be averaged
        
        self.SpmCount = self.daq.ai.samplesPerTrig*round(self.rSR*0.5) # process data every 0.5 sec
        self.databuffer = [] # for @process_data
        self.timebuffer = [] # for @process_data
        
        # setup Callbacks
        self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
        self.daq.ai.samplesAcquiredFcn = (self.process_data,) # ',' makes it a tuple
        self.daq.ai.trigFcn = (self.AIwaiting,)

        #TODO - setup KeyPressFcn etc.


        #%% 
        '''
        Connect signals and slots
        '''
        self.disptimer.timeout.connect(self.update_plot)
        self.Start_Stop.clicked.connect(self.Start_Stop_Callback)

        self.AxesSwitch.currentIndexChanged.connect(self.AxesSwitch_Callback)
        self.Auto_axes.clicked.connect(self.Auto_axes_Callback)
        self.uplimdown2.clicked.connect(self.push_ylimAdj)
        self.uplimdown025.clicked.connect(self.push_ylimAdj)
        self.uplimup2.clicked.connect(self.push_ylimAdj)
        self.uplimup025.clicked.connect(self.push_ylimAdj)
        self.lowlimdown2.clicked.connect(self.push_ylimAdj)
        self.lowlimdown025.clicked.connect(self.push_ylimAdj)
        self.lowlimup2.clicked.connect(self.push_ylimAdj)
        self.lowlimup025.clicked.connect(self.push_ylimAdj)
        self.Lock.clicked.connect(self.Lock_Callback)
        self.Set_ylim.clicked.connect(self.Set_ylim_Callback)

        self.Set_PSD.clicked.connect(self.Set_PSD_Callback)
        self.PhaseShift.clicked.connect(self.PhaseShift_Callback)
        self.PSDadd90.clicked.connect(self.PSDadd90_Callback)
        self.AutoPhase.clicked.connect(self.AutoPhase_Callback)
        self.PSD_slider.valueChanged.connect(self.PSD_slider_Callback)
        self.Cm.currentIndexChanged.connect(self.Cm_Callback)
        self.Auto_FP.stateChanged.connect(self.Auto_FP_Callback)

        for key in self.fcheck.keys():
            exec(f'self.{key}.stateChanged.connect(self.FilterCheck_Callback)')
        self.Set_filter.clicked.connect(self.Set_filter_Callback)
        self.Set_filter2.clicked.connect(self.Set_filter2_Callback)
        self.FilterSwitch.currentIndexChanged.connect(self.FilterSwitch_Callback)

        self.slider1.valueChanged.connect(self.slider_Callback)
        self.slider2.valueChanged.connect(self.slider_Callback)
        #TODO - other GUI components
    
    # End of __init__() -------------------------------------------------------
    '''
    Function and class definition
    '''
    #%% Utility -------------------------------------------------------
    class kwarg2var:
        #container class; used for mimicing the struct data type
        def __init__(self, **kwargs):
            #print(type(kwargs)) #dict
            for key, value in kwargs.items():
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
        axes.setRange(xRange=lim,padding=0)

    def ylim(self,axes,lim):
        # lim: tuple
        if lim == 'auto':
            axes.getViewBox().enableAutoRange(axis='y')
        elif lim == 'manual':
            axes.getViewBox().disableAutoRange(axis='y')
        elif lim == 'range': #get current range
            return axes.getViewBox().viewRange()[1] # [[x0,x1],[y0,y1]]
        else:
            axes.setRange(yRange=lim,padding=0)
    
    def pseudoDataGenerator(self,Nsp):
        return [randint(20, 40) for _ in range(Nsp)]

    def update_plot(self):
        #TODO
        XData = list(range(1000))
        YData1 = self.pseudoDataGenerator(len(XData))
        YData2 = self.pseudoDataGenerator(len(XData))
        self.plot1.setData(XData,YData1)
        self.plot2.setData(XData,YData2)

    def process_data(self,_,*args):
        '''
        process data every ~0.5sec.
        AICh0: current, for direct recording and PSD; AICh1:current, e.g. from Ampero
        Ch1:Capacitance; Ch2:Conductance; Ch3:Current; Ch4:Ampero current
        _ is the eventdata from daqx
        '''
        if len(args) == 0:
            getAll = False
        else:
            getAll = args[0]
        
        # extract data
        if getAll: #will be used in Pulse_Callback
            self.timebuffer, self.databuffer = self.daq.ai.getdata() #process all remaining data
        else:
            self.timebuffer, self.databuffer = self.daq.ai.getdata(self.SpmCount)

        # process data
        if self.algorithm >= 2: #SQA
            if self.autofp and self.autorange: #auto-range
                if self.algorithm == 2: #I-SQA
                    Time,PSD2,PSD1,Curr,AICh2,asymp,peak,tau = self.CapEngine(2,taufactor = 3, endadj = -5)
                else: #Q-SQA, different taufactor/consecpt
                    Time,PSD2,PSD1,Curr,AICh2,asymp,peak,tau = self.CapEngine(3,taufactor = 1, endadj = -5)
            else: #no auto-range
                Time,PSD2,PSD1,Curr,AICh2,asymp,peak,tau = self.CapEngine(self.algorithm)

            Cap,Cond,Ra = self.SqAlgo(asymp,peak,tau)
            self.PSDofSQA = np.hstack((self.PSDofSQA,np.vstack(PSD2,PSD1)))

        elif self.algorithm == 1: #PSD
            Time,Cap,Cond,Curr,AICh2 = self.CapEngine(1)
            Ra = np.empty_like(Time)
            Ra.fill(np.nan)
        else: #Hardware
            Time,Cap,Cond,Curr = self.CapEngine(0)

        self.aitime = np.concatenate((self.aitime,Time))
        if self.algorithm == 0:
            self.aidata = np.hstack((self.aidata,np.vstack(Cap,Cond,Curr)))
        else:
            self.aidata = np.hstack((self.aidata,np.vstack(Cap,Cond,Curr,AICh2,Ra)))

        #TODO - translate the following
        # if Cap7_state.pulse.pulsing
        #     Cap7_state.pulse.data(end).rawData = cat(1,Cap7_state.pulse.data(end).rawData,...
        #         [handles.timebuffer(:,1),handles.databuffer(:,2:3)]);
        # end

        # if Cap7_state.pulse.JustDone
        #     Cap7_state.pulse.JustDone = 0;
        #     Cap7_state.pulse.pulsing = false;
        #     %blank C,G,Ra.
        #     handles.aidata(handles.Pulselog(end).index(1,1):handles.Pulselog(end).index(1,2),...
        #         [1,2,5]) = NaN;
        #     %assign data
        #     temp = isnan(Cap7_state.pulse.data(end).rawData(:,1));
        #     Cap7_state.pulse.data(end).rawData(temp,:) = []; %remove NaN
        #     %Cap7_state.pulse.data(end+1).mV = handles.Pulselog(end).output*Cap7_state.daq.aoCh2convert; %to mV
        #     Cap7_state.pulse.data(end).mV = handles.Pulselog(end).output*Cap7_state.daq.aoCh2convert; %to mV, TW161217
        #     Cap7_state.pulse.data(end).Ch34 = handles.aidata(handles.Pulselog(end).index(1,1):...
        #         handles.Pulselog(end).index(1,2),[3,4]);
        #     if Cap7_state.pulse.notPartOfPulseTriggers ~= 0
        #         Cap7_state.pulse.data(end).rawData(1:Cap7_state.pulse.notPartOfPulseTriggers*handles.ai.SamplesPerTrigger,:) = []; %TW161218, delete non-pulse data
        #     end
        #     Cap7_state.pulse.data(end).rawData((handles.ai.SamplesPerTrigger*numel(handles.Pulselog(end).output))+1:end,:) = []; %TW161218, delete non-pulse data
        #     Cap7_state.pulse.data(end).rawData(:,1) = Cap7_state.pulse.data(end).rawData(:,1) - Cap7_state.pulse.data(end).rawData(1,1);
        # end

        # if handles.rxrindex
        #     Spm = round(Cap7_state.daq.aiSR*(2/handles.PSDfreq/1000));
        #     if Spm > handles.aiSamplesPerTrigger
        #         Spm = handles.aiSamplesPerTrigger;
        #     end
        #     handles.rxr = cat(1,handles.rxr,[handles.timebuffer(1:Spm),handles.databuffer(1:Spm,:)]);
        #     handles.rxr = cat(1,handles.rxr,[NaN NaN NaN NaN]);
        # end

    def CapEngine(self,algorithm,taufactor = -1, endadj = 0):
        '''
        Hardware: (time,Cap/AICh0,Cond/AICh1,Curr/AICh2) = CapEngine(0) #Note - AICH2 will be disabled in the context menu
        PSD: (time,Cap,Cond,current,AICh2) = CapEngine(1)
        SQCF: (time,PSD90,PSD,current,AICh2,asymp,peak,tau) = CapEngine(2,(opt)taufactor,(opt)endadj)
        SqQ: (time,PSD90,PSD,current,AICh2,asymp,peak,tau) = CapEngine(3,(opt)taufactor,(opt)endadj)

        for SQCF and SqQ - 
        * taufactor and endadj are used for adjusting curve-fitting range (i.e. from lastmax to firstmin in the DLL)
        * if taufactor < 0 -> no adjustment; else: taufactor = 1/exp(taufactor) and pass to the DLL
        * firstmin = Cpickend2(dataB, SPC, lastmax, taufactor) + endadj; in the DLL
        '''
        Nref = self.PSDref.size #self.PSDref: [] -> np.ndarray
        ppch = int(self.timebuffer.size/self.daq.ai.samplesPerTrig) #points per channel
        TIME = np.empty(ppch,dtype=np.float64)
        CAP = np.empty(ppch,dtype=np.float64)
        COND = np.empty(ppch,dtype=np.float64)
        CURR = np.empty(ppch,dtype=np.float64)

        self.lib.Dfilter(0,self.timebuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
            TIME.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        
        if algorithm == 0: #Hardware
            self.lib.Dfilter(int(self.fcheck['rf0']),self.databuffer[0,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
                CAP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf1']),self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
                COND.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf2']),self.databuffer[2,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
                CURR.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))

            return TIME,CAP,COND,CURR

        else: #PSD, SQA
            AICH2 = np.empty(ppch,dtype=np.float64)
            self.lib.Dfilter(int(self.fcheck['rf1']),self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
                CURR.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf2']),self.databuffer[2,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.daq.ai.samplesPerTrig),int(self.filterv2p),ppch,
                AICH2.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))

            if algorithm >= 2: #SQA
                ASYMP = np.empty(ppch,dtype=np.float64)
                PEAK = np.empty(ppch,dtype=np.float64)
                TAU = np.empty(ppch,dtype=np.float64)
                if taufactor >= 0:
                    taufactor = 1/np.exp(taufactor)
                
                if algorithm == 2: #I-SQA
                    self.lib.SqCF(self.databuffer[0,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.timebuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        int(self.daq.ai.samplesPerTrig),float(taufactor),int(endadj),ppch,
                        ASYMP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        PEAK.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        TAU.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
                else: #Q-SQA
                    interval = (self.timebuffer[self.daq.ai.samplesPerTrig-1] - self.timebuffer[0]) / (self.daq.ai.samplesPerTrig - 1) #calculate time interval between data points
                    self.lib.SqQ(self.databuffer[0,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.timebuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        int(self.daq.ai.samplesPerTrig),float(taufactor),int(endadj),ppch,float(interval),
                        ASYMP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        PEAK.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        TAU.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            #also do PSD even the SQA is selected
            self.lib.PSD(self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                self.PSD90.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                Nref,int(self.daq.ai.samplesPerTrig),ppch,
                CAP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.PSD(self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                self.PSDref.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                Nref,int(self.daq.ai.samplesPerTrig),ppch,
                COND.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            if algorithm == 1: #PSD
                return TIME,CAP,COND,CURR,AICH2
            else: #SQA
                return TIME,CAP,COND,CURR,AICH2,ASYMP,PEAK,TAU
            
    def SqAlgo(self,asymp,peak,tau):
        '''
        Calculate C, G, Ra and adjust the square wave form is so desired
        If amplifier gain alpha*beta == 1
            1 unit = 10pF, 1nS, 1MOhms
        '''
        taufactor = 2
        maxA = []
        meantau = []
        V = self.PSDamp
        duration = 1/self.PSDfreq/2000
        newfreq = self.PSDfreq
        newamp = V
        #TODO - translate the following
        # try
        #     if (~isequal(get(handles.Cm,'ForegroundColor'),[0 0 0]))&&(~isnan(tau(1,1)))
        #         set(handles.Cm,'ForegroundColor','black');
        #     elseif (isequal(get(handles.Cm,'ForegroundColor'),[0 0 0]))&&(isnan(tau(1,1)))
        #         set(handles.Cm,'ForegroundColor','red');
        #     end
        #     if (isequal(get(handles.Cm,'BackgroundColor'),[1 0 0]))&&(max(peak(~isnan(peak))) < 10)
        #         set(handles.Cm,'BackgroundColor',get(handles.figure1,'Color'));
        #     elseif (~isequal(get(handles.Cm,'BackgroundColor'),[1 0 0]))&&(max(peak(~isnan(peak))) >= 10)
        #         set(handles.Cm,'BackgroundColor','red');
        #     end
        # end

        F = V/2/(asymp*(1-np.exp(-duration/tau))+peak)
        Ra = -F*(-2+np.exp(-duration/tau))
        Cond = asymp/(F*(peak-asymp))
        Cap = tau*((1/Ra)+Cond)*100000
        Cond = Cond*1000

        # If amplifier gain alpha*beta == 1
        #     1 unit = 10pF, 1nS, 1MOhms

        if self.autofp and self.autofreq:
            maxA = peak.mean()
            meantau = tau.mean()
            if maxA >= 15: #20 originally
                newamp = 10*self.PSDamp/15
                if newamp > 50:
                    newamp = 50
            elif maxA < 5: #2 originally
                newamp = 20*self.PSDamp
            #TODO - paused 1/10/2025
        #     if ((0.0005/handles.PSDfreq) > (meantau*taufactor)) %higher freq is better
        #         %newfreq = handles.PSDfreq-0.2; %move 0.2kHz gradually
        #         newfreq = 0.001/(meantau*taufactor*2); %in kHz
        #         %assignin('base','newfreq',newfreq);
        #         if newfreq < handles.rSR*2/1000
        #             newfreq = handles.rSR*2/1000;
        #         elseif newfreq > 10
        #             newfreq = 10;
        #         end
        #         %disp('entered');
        #     end
        #     if (newfreq ~= handles.PSDfreq) || (newamp ~= handles.PSDamp)
        #         [data,PSDfreq,PSDamp] = Wavecalc(FH,newfreq,newamp);
        #         if (abs(PSDfreq-handles.PSDfreq)>0.1) || (abs(PSDamp-handles.PSDamp)>5)
        #             %disp('entered');
        #             %abs(PSDfreq-handles.PSDfreq)
        # %             S = size(data); %v1
        # %             handles.aodata = [data,zeros(S(1,1),1)]; %v1
        #             handles.aodata = data; %v2
        #             handles.PSDfreq = PSDfreq;
        #             handles.PSDamp = PSDamp;
        #             %handles.autofreq = 0;
        #             handles.PSDlog = cat(1,handles.PSDlog,{handles.aitime(length(handles.aitime),1),...
        #                 handles.PSDfreq,handles.PSDamp,NaN,'Square'});
        #             set(handles.PSD_freq,'String',num2str(handles.PSDfreq,4));
        #             set(handles.PSD_amp,'String',num2str(handles.PSDamp,4));
        #             %set(handles.context_autofreq,'Checked','off');
        #             guidata(FH,handles);
        #             stop(handles.ao);
        #             putdata(handles.ao,handles.aodata);
        #             start(handles.ao);
        #         end
        #     end
        # end
        # output = [Cap,Cond,Ra];

    def AIwaiting(self,_):
        '''
        aiTriggerFcn for Start_Stop button
        _ is the eventdata from daqx
        '''
        self.daq.ai.trigFcn = None
        self.Start_Stop.setText('Started')
        self.Start_Stop.setStyleSheet('color:green')

    def resume(self):
        '''
        aoStopFcn for Pulse
        '''
        raise NotImplementedError

    def FilterCalc(self,filterp,filtermaxp):
        '''
        Update the number of data points for averaging in the digital pre-filter (for raw data).
        Ensures that the sine/square wave can be cancelled so DC current can be extracted.
        '''
        ppw = self.daq.ai.sampleRate/self.PSDfreq/1000 #points per wave
        if (ppw > filtermaxp):
            filterv2p = 1
        else:
            filterv2p = round(round(filterp/ppw)*ppw)
            if filterv2p > filtermaxp:
                filterv2p = round((filtermaxp//ppw)*ppw)
            elif filterv2p < ppw:
                filterv2p = round(ppw)
        return filterv2p

    def Refcalc(self):
        '''
        Calculate PSD reference waveform
        '''
        PPS = (self.daq.ai.sampleRate/(self.PSDfreq*1000)) #points per sine wave
        L = int((self.daq.ai.samplesPerTrig//PPS)*PPS) #make sure that the DC noise can be cancled
        T = L/self.daq.ai.sampleRate #Note - set np.linspace(...,endpoint = False)
        P = self.PSDphase*np.pi/180
        F = self.PSDfreq*1000
        self.PSDref = np.sin(np.linspace((P+(np.pi/2)),((P+(np.pi/2))+(2*np.pi*F*T)),L,endpoint=False))
        self.PSD90 = np.sin(np.linspace((P+np.pi),(P+(np.pi*(1+(2*F*T)))),L,endpoint=False))

    def Wavecalc(self,freq,amp):
        '''
        Generate AO output waveform
        '''
        L = round(self.daq.ao.sampleRate/self.rSR) #total samples
        N = self.daq.ao.sampleRate//(freq*1000) #samples per wave
        A = abs(amp/self.daqdefault.aoExtConvert)
        triggerpt = ceil(2/self.daq.ai.sampleRate*self.daq.ao.sampleRate)
        if A > 20:
            A = 20
        if (self.algorithm >=2): #SQA
            if N%2 != 0: #even samples in a single wave
                N = N+1
            elif N == 0:
                N = 2
            L = round(L/N)*N; #re-calculate samples per trigger
            freq = self.daq.ao.sampleRate/N/1000; #in kHz
            output = np.empty(L,dtype = np.float64)
            output = self.lib.SqWaveCalc(int(L),int(N),A,output.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        elif self.algorithm ==1: #PSD, produce sine wave
            T = L/self.daq.ao.sampleRate
            P = np.pi/2 #pi/2 shifted, in order to put the trigger at the top -> this seems unnecessary since we use digital trigger now
            cycles = round(freq*1000*(L/self.daq.ao.sampleRate))
            N = L/cycles
            freq = cycles/(L/self.daq.ao.sampleRate)/1000
            output = ((A/2)*np.sin(np.linspace(P,(P+(2*np.pi*freq*1000*T)),L,endpoint=False)))
        else: #Hardware
            output = np.zeros(L)
        
        trigsig = np.zeros(L) #trigger signal
        trigsig[0:triggerpt] = 5 #1V is not enough to trigger MCC board...
        output = np.vstack((trigsig,output))
        
        amp = A*abs(self.daqdefault.aoExtConvert); #in mV
        return output,freq,amp
    
    #%% Callbacks -------------------------------------------------------
    def Start_Stop_Callback(self):
        #TODO
        if self.Start_Stop.isChecked(): #start
            #TODO - translate below
            # if Cap7_state.changed
            #     if ~dlg_SaveData(handles.figure1) %canceled or no selection
            #         set(hObject,'Value',0);
            #         return
            #     end
            # end
            self.rSR = abs(float(self.RecordSampleRate.text()))
            if self.rSR > 500:
                self.rSR = 500
                self.RecordSampleRate.setText(str(self.rSR))
            elif self.rSR < 5:
                self.rSR = 5
                self.RecordSampleRate.setText(str(self.rSR))
            self.PSDamp = [] #make it empty in order to enter the 'if' codes in @Set_PSD_Callback
            self.PSDfreq = float(self.PSD_freq.text()) #kHz
            self.PSDphase = float(self.PSD_phase.text()) #degree

            # adjust AI properties
            self.daq.ai.samplesPerTrig = int(((1/self.rSR)*0.9)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
            self.SpmCount = self.daq.ai.samplesPerTrig*round(self.rSR*0.5) # process data every 0.5 sec
            self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
            self.daq.ai.trigFcn = (self.AIwaiting,)
            
            self.filterv2p = round((float(self.filterset.text())/1000)*self.daq.ai.sampleRate) #points to be averaged
            self.fwindow = abs(int(self.filterset2.text())) #samples for the moving filter
            filtermaxp = self.daq.ai.samplesPerTrig #calculate maximal averaging points
            if self.filterv2p > filtermaxp:
                self.filterv2p = filtermaxp
                self.filterset.setText(str(1000*filtermaxp/self.daq.ai.sampleRate))
            elif self.filterv2p < 1:
                self.filterv2p = 1
                self.filterset.setText(str(1/self.daq.ai.sampleRate))
            if self.fwindow == 0:
                self.fwindow = 1
                self.filterset2.setText('1')

            #TODO - translate below
            # if strcmpi(get(hObject,'HitTest'),'off') %return if data processing is in progress
            #     set(hObject,'Value',0);
            #     return
            # end
            # set(handles.Start_Stop,'HitTest','off');
            self.aidata = []
            self.aitime = []
            self.PSDofSQA = []
            self.Pulselog = []
            self.Stdfactor = [] # convert volt to fF
            self.labelindex = []
            self.slider1.setValue(0)
            self.slider1v2p = round(self.slider1.value()*self.rSR) #for @update_plot, @slider1_Callback
            self.slider2v2p = round(self.slider2.value()*self.rSR) #for @update_plot, @slider2_Callback
            #TODO - translate below
            # set(handles.xlim1,'String','0');
            # set(handles.xlim2,'String','0');
            # set(handles.figure1,'Name',handles.version.Shell);
            # set(Cap7_gh.NotePad.figure1,'Name',handles.version.Shell);
            # delete(findobj('parent',handles.axes1,'Type','text'));
            # delete(findobj('parent',handles.axes2,'Type','text'));
            # set(handles.group_stop(1,:),'Enable','off');
            # set(handles.group_start(1,:),'Enable','on');
            self.Start_Stop.setText('Waiting')
            self.Start_Stop.setStyleSheet('color:rgb(225,135,0)')

            #adjust AO property
            if self.daq.ao.isrunning:
                self.daq.ao.stop()
            
            self.daq.ao.stop() #might be started again @resume
            sleep(0.003)
            #TODO - translate below
            # if strcmpi(get(handles.context_TTL,'Checked'),'off')
            #     set(handles.ao,'TriggerType','Immediate');
            # else
            #     set(handles.ao,'TriggerType','HwDigital');
            #     set(handles.ao,'HwDigitalTriggerSource','PFI0');
            #     %set(handles.ao,'TriggerFcn',{@AIwaiting,gcf});
            # end

            self.daq.ai.start()
            self.Set_PSD_Callback() #this will start the AO
            #TODO - translate below
            # if (handles.algorism ~= 1)&&(~handles.menuindex(1,1))
            #     MenuSwitcher(gcf,1); %for SQA
            # elseif (handles.algorism == 1)&&(handles.menuindex(1,1))
            #     MenuSwitcher(gcf,0); %for PSD
            # end
            #self.disptimer.start()
        else: #stop
            self.daq.ai.stop()
            self.daq.ao.stop()
            self.Start_Stop.setText('Stopped')
            self.Start_Stop.setStyleSheet('color:red')
            if self.AutoPhase.isChecked():
                self.AutoPhase.setText('PAdj')
                self.AutoPhase.setChecked(False)
            self.daq.ao.putvalue([0,0])
            #TODO - translate below
            # if ~isempty(handles.rxr) %TW150503: added back
            #     assignin('base','rxr',handles.rxr);
            # end
            # if ~isempty(Cap7_state.pulse.data)
            #     assignin('base','Pulses',Cap7_state.pulse.data);
            # end
            # assignin('base','PSDlog',handles.PSDlog); %TW150503: added back
            # assignin('base','Pulselog',handles.Pulselog); %TW150503: added back
            # set(handles.group_filter(1,:),'Enable','off');
            # set(handles.group_filter(1,:),'Enable','on');
            # set(handles.group_stop(1,:),'Enable','on');
            # set(handles.group_start(1,:),'Enable','off');
            # set(handles.Start_Stop,'HitTest','on');
            self.aodata = [0,0]
            # handles.aidata2 = handles.aidata; %for Kseal adjusted data; %TW141013
            # guidata(handles.figure1,handles);
            # Cap7_state.changed = true;
            # ChangedOrSaved(handles.figure1);
            # %assignin('base','aodata',handles.aodata);
            if not self.aitime:
                return
            else:
                pass
                #TODO - translate below
                # edit_Kseal_Callback(handles.edit_Kseal, eventdata, guidata(gcf)); %TW141015
                # %Show_update_Callback(hObject, eventdata, handles); %will be evoked in
                # %edit_Kseal_Callback %TW141023
            #self.disptimer.stop()

    def AxesSwitch_Callback(self):
        self.limsetindex[0] = self.AxesSwitch.currentIndex()
        self.Auto_axes.setChecked(self.limsetindex[0]+1)
        
    def Set_ylim_Callback(self):
        if self.limsetindex[0] == 0:
            axes = self.axes1
        elif self.limsetindex[0] == 1:
            axes = self.axes2
        else:
            axes = self.axes3
        #print(axes.getViewBox().viewRange())
        if self.Auto_axes.isChecked():
            self.Auto_axes.setChecked(False)
            self.limsetindex[self.limsetindex[0]+1] = False

        lim1 = float(self.ylim1.text())
        lim2 = float(self.ylim2.text())
        if lim1 < lim2:
            self.ylim(axes,(lim1,lim2))
        elif lim1 > lim2:
            self.ylim(axes,(lim2,lim1))
            self.ylim1.setText(str(lim2))
            self.ylim2.setText(str(lim1))
        else:
            self.ylim(axes,'auto')
            self.Auto_axes.setChecked(True)
            self.limsetindex[self.limsetindex[0]+1] = True
        #TODO - disable Lock if set the middle panel?

    def Auto_axes_Callback(self):
        if self.limsetindex[0] == 0:
            axes = self.axes1
        elif self.limsetindex[0] == 1:
            axes = self.axes2
        else:
            axes = self.axes3
        
        if self.Auto_axes.isChecked():
            self.ylim(axes,'auto') # auto is on
            self.limsetindex[self.limsetindex[0]+1] = True
        else:
            self.ylim(axes,'manual') # auto is off
            self.limsetindex[self.limsetindex[0]+1] = False
            if (self.limsetindex[0] == 1):
                self.Lock.setChecked(False)

    def push_ylimAdj(self):
        if self.limsetindex[0] == 0:
            axes = self.axes1
        elif self.limsetindex[0] == 1:
            axes = self.axes2
        else:
            axes = self.axes3
        
        sender = self.sender()
        uplow = sender.objectName()[0] #'u' for upper lim, 'l' for lower lim
        value = float(sender.text())
        #print(f'{uplow}: {value}')
        if self.Auto_axes.isChecked(): #if Auto is on
            self.Auto_axes.setChecked(False)
            if (self.limsetindex[0] == 1):
                self.Lock.setChecked(False)

            self.limsetindex[self.limsetindex[0]+1] = False
        lim = self.ylim(axes,'range')
        if (uplow == 'u') and (lim[1]+value > lim[0]): # adjust upper lim
            self.ylim2.setText(f'{lim[1]+value:.2f}')
        elif (uplow == 'l') and (lim[0]+value < lim[1]): # adjust lower lim
            self.ylim1.setText(f'{lim[0]+value:.2f}')
        else:
            return
        self.Set_ylim_Callback()

    def Lock_Callback(self):
        if self.Lock.isChecked(): #Lock is on
            if (self.limsetindex[0] == 1) and (self.limsetindex[2] == False): #Mark auto-axis if it's axes2
                self.Auto_axes.setChecked(True)
            self.limsetindex[2] = True
        else:
            self.ylim(self.axes2,'auto')

    def slider_Callback(self):
        value = self.sender().value() #int
        if self.sender().objectName() == 'slider1': #slider1 or slider2
            self.slider1v2p = round(value*self.rSR)
            self.text_slider1.setText(str(value))
        else: #slider2
            self.slider2v2p = round(value*self.rSR)
            self.text_slider2.setText(str(value))
        #TODO - remaining display control code
        #Note - Page change won't emit sliderReleased() signal. i.e. cannot put disp update code in the corresponding callback
    
    def Set_PSD_Callback(self):
        if not self.Start_Stop.isChecked():
            return #only continue if the program is running

        PSDfreq = abs(float(self.PSD_freq.text()))
        PSDamp = abs(float(self.PSD_amp.text()))
        if self.algorithm >= 2: #SQA
            if PSDfreq > 2.5:
                PSDfreq = 2.5
            elif PSDfreq < 2*self.rSR/1000:
                PSDfreq = 2*self.rSR/1000

        if (PSDfreq != self.PSDfreq) or (PSDamp != self.PSDamp):
            self.aodata, PSDfreq, PSDamp = self.Wavecalc(PSDfreq,PSDamp)
            self.PSDfreq = PSDfreq
            self.PSDamp = PSDamp
            self.PSD_freq.setText(str(self.PSDfreq))
            self.PSD_amp.setText(str(self.PSDamp))
            #TODO - translate below
            # if get(handles.Pulse,'Value')
            #     stop(handles.ao);
            # end
            self.daq.ao.stop() #ao might be started again in @resume
            #TODO - translate below
            # if ~strcmpi(handles.ao.TriggerType,'Immediate') && (handles.ai.TriggersExecuted ~= 0)
            #     set(handles.ao,'TriggerType','Immediate');
            # end
            # %assignin('base','aodata',handles.aodata);
            self.daq.ao.putdata(self.aodata)
            self.Set_filter_Callback() #adjust filter setting accordingly
            self.daq.ao.start()
           
        self.PSDphase = float(self.PSD_phase.text())
        P = abs(self.PSDphase)
        if P > 360:
            self.PSDphase = np.sign(self.PSDphase)*(P%360)
        if self.PSDphase > 180:
            self.PSDphase = self.PSDphase-360
        elif self.PSDphase < -180:
            self.PSDphase = self.PSDphase+360
        self.PSD_phase.setText(f'{self.PSDphase:.2f}')
        self.PSD_slider.setValue(round(100*self.PSDphase/180)) #slider range is -18000 to 18000, int only

        #PSDlog
        L = len(self.aitime)
        if L != 0:
            if self.daq.ai.isrunning:
                self.PSDlog.append([self.aitime[-1],self.PSDfreq,
                                    self.PSDamp,self.PSDphase,self.Cm.currentText()])
        else:
            self.PSDlog = [[0,self.PSDfreq,self.PSDamp,self.PSDphase,self.Cm.currentText()]]
        
        self.Refcalc()

    def PhaseShift_Callback(self):
        pass #TODO
    
    def PSDadd90_Callback(self):
        pass #TODO

    def AutoPhase_Callback(self):
        pass #TODO

    def PSD_slider_Callback(self):
        pass #TODO

    def Cm_Callback(self,index):
        '''
        index 0:Hardware, 1:PSD, 2:I-SQA, 3:Q-SQA
        '''
        #print(index)
        self.algorithm = index
        #TODO - prohibit transition from Hardware to any other algorithms or vice versa during acquisition
        #TODO - full implementation

    def Auto_FP_Callback(self,index):
        '''
        index 0:unchecked, 1:partially checked (not allowed here),2:checked
        '''
        self.autofp = True if index > 1 else False
        #print(index)
        #TODO - full implementation

    def FilterCheck_Callback(self):
        '''
        objectName:
        prefilter - rf0, 1, 2
        moving filter - mf0, 1, 2, 3, 4
        '''
        self.fcheck[self.sender().objectName()] = self.sender().isChecked()

    def Set_filter_Callback(self): #pre-filter on raw data
        filtermaxp = self.daq.ai.samplesPerTrig #calculate maximal averaging points
        filterp = round(abs(float(self.filterset.text())/1000)*self.daq.ai.sampleRate)
        self.filterv2p = self.FilterCalc(filterp,filtermaxp)
        if (self.filterv2p == 1):
            self.filterset.setText('0')
        else:
            self.filterset.setText(str(1000*self.filterv2p/self.daq.ai.sampleRate))

    def Set_filter2_Callback(self): #moving filter
        self.fwindow = abs(round(float(self.filterset2.text())))
        if self.fwindow == 0:
            self.fwindow = 1
            self.filterset2.setText('1')
        #TODO - translate the following
        # if strcmpi(handles.ai.running,'off')
        #     Show_update_Callback(hObject, eventdata, handles);
        # end
    
    def FilterSwitch_Callback(self,index):
        '''
        0:Bypass; 1:Mean; 2:Median
        '''
        self.fswitch = index
        #TODO - translate the following
        # if strcmpi(handles.ai.running,'off')
        #     Show_update_Callback(hObject, eventdata, handles);
        # end
    

#%% -------------------------------------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
