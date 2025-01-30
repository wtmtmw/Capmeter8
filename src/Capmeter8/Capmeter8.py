from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu
from PyQt6.QtCore import QTimer, QPoint
from PyQt6.QtGui import QAction, QActionGroup #for context menu etc.
# from pyqtgraph import PlotWidget, plot #for packaging only if loading .ui directly? need to test...
import sys, traceback, ctypes
import pyqtgraph as pg
from pathlib import Path
import numpy as np
from math import ceil
from time import sleep
from random import randint
from daqx.util import createDevice

class MainWindow(QMainWindow):
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

        self.disp = self.kwarg2var(dispindex = [0,1,2], # 0-based
                                   chcolor = ['r','b',(204,0,204),(64,153,166),'k'], #display color of the channel
                                   slider0range = 120,
                                   slider1range = 50,
                                   invertindex = [False,False,False], #[axes0,axes1,axes2]
                                   )
        
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
        self.menuindex = [0,'p','p','p'] # [context menu ID, axes0 PSD or SQA, axes1 PSD or SQA, axes2 PSD or SQA], modified in @MenuSwitcher
        # context menu ID: 0-normal, 1-PSDofSQA; displayed data 'p'-PSD, 's'-SQA
        self.limsetindex = [self.AxesSwitch.currentIndex(),True,True,True]; #[axis #,Auto,Auto,Auto], axes is 0-based
        self.Auto_axes.setChecked(self.limsetindex[self.limsetindex[0]+1])

        self.plot0 = self.iniAxes(self.axes0,self.disp.chcolor[self.disp.dispindex[0]])
        self.plot1 = self.iniAxes(self.axes1,self.disp.chcolor[self.disp.dispindex[1]])
        self.plot2 = self.iniAxes(self.axes2,self.disp.chcolor[self.disp.dispindex[2]])

        self.labelindex = [] #[dispindex,time,data,'string'] 0-based
        self.slider0.setMaximum(self.disp.slider0range)
        self.text_slider0.setText(f'{self.slider0.value():.0f}')
        self.slider1.setMaximum(self.disp.slider1range)
        self.text_slider1.setText(f'{self.slider1.value():.0f}')
        #TODO - implement the followings
        self.fswitch = self.FilterSwitch.currentIndex()
        self.shiftvalue = float(self.Phase_Shift.text())
        self.shiftswitch = -1 #0:Csqa, 1:Gs qa, -1:G and C for cross correlation
        self.Stdfactor = [] #convert volt to fF

        #TODO - other display-related settings

        '''
        List of DAQ-related variables
        '''
        self.disptimer = QTimer() #connected to update_plot()
        self.disptimer.setInterval(1000) #in ms
        self.rSR = abs(float(self.RecordSampleRate.text()))
        self.samplesPerTp = None # samples per timepoint = round(self.daq.ai.sampleRate/self.rSR) # new for Cap8. For generating data points in CapEngine etc.
        self.aidata = [] # np.ndarray; M-by-Timepoint matrix, where M is the number of parameters/channels
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
        self.PSDlog = [] #List of [[time,kHz,mV,degree,algorithm],...]
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
            self.daq.ai.trigRepeat = 1 # one trigger, continuous acquisition
            self.daq.ai.aqMode = 'background'
            self.daq.ai.grounding = 'single-ended'
            self.daq.ai.sampleRate = self.daqdefault.aiSR
            #self.daq.ai.samplesPerTrig = int(((1/self.rSR)-0.001)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
            self.daq.ai.samplesPerTrig = 'inf' #This is actually optional. Put it here for clarity only
            self.samplesPerTp = round(self.daq.ai.sampleRate/self.rSR) # new for Cap8. For generating data points in CapEngine etc.
        except:
            print('AI error in OpeningFcn')
            self.reader = True
        finally:
            pass
            #TODO - handle if samplesPerTrig < 1 e.g. rSR = 1000Hz
        
        # the calculation of sliderv2p as it behaves differently in MATLAB and PyQt
        #TODO - remove sliderv2p in future release
        self.slider0v2p = round(self.slider0.value()*self.rSR) #for @update_plot, @slider0_Callback
        self.slider1v2p = round(self.slider1.value()*self.rSR) #for @update_plot, @slider1_Callback
        self.filterv2p = round((float(self.filterset.text())/1000)*self.daq.ai.sampleRate) #points to be averaged
        
        self.SpmCount = self.samplesPerTp*round(self.rSR*0.5) # process data every 0.5 sec
        self.databuffer = [] # for @process_data
        self.timebuffer = [] # for @process_data
        
        # setup Callbacks
        self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
        self.daq.ai.samplesAcquiredFcn = lambda eventdata: self.process_data()
        self.daq.ai.trigFcn = lambda eventdata: self.AIwaiting()
        #TODO - translate below
        # set(handles.ao,'StopFcn','');
        # set(handles.ao,'TriggerFcn','');
        # set(handles.ao,'RuntimeErrorFcn',{@AOrecover,gcf});
        # set(handles.group_keypress(1,:),'KeyPressFcn',{@KeyPress,gcf});
        # set(handles.group_stop(1,1:end-3),'KeyPressFcn',{@KeyPress2,gcf});

        #TODO - setup KeyPressFcn etc.
        #TODO - translate below
        # %launch reader mode if eg. DAQ is not installed
        # if handles.reader
        #     set(handles.group_reader(1,:),'Enable','off');
        #     try
        #         handles.ai.running = 'off';
        #     end
        #     try
        #         handles.ao.running = 'off';
        #     end
        #     guidata(hObject,handles);
        #     disp('Reader mode is launched');
        # end

        #adjust displayed channel
        if self.algorithm >= 2:
            self.MenuSwitcher(1) #SQA
        else:
            self.MenuSwitcher(0) #PSD

        #ChangedOrSaved(handles.figure1);


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

        self.slider0.valueChanged.connect(self.slider_Callback)
        self.slider1.valueChanged.connect(self.slider_Callback)
        self.Show.clicked.connect(self.Show_Callback)

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

        # Set up context menu
        # Note - cannot connect context menu callback using the loop below. The default channel will be wrong (Ch4-Ra for all axes)...
        # for ax in [self.axes0,self.axes1,self.axes2]:
        #     ax.getPlotItem().setMenuEnabled(False) #disable default pyqtplot context menu
        #     ax.customContextMenuRequested.connect(lambda pos: self.create_context_axes_b(ax,pos)) #connect to custom context menu
        self.axes0.getPlotItem().setMenuEnabled(False) #disable default pyqtplot context menu
        self.axes0.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes0,pos)) #connect to custom context menu
        self.axes1.getPlotItem().setMenuEnabled(False) #disable default pyqtplot context menu
        self.axes1.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes1,pos)) #connect to custom context menu
        self.axes2.getPlotItem().setMenuEnabled(False) #disable default pyqtplot context menu
        self.axes2.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes2,pos)) #connect to custom context menu
        
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
        '''
        Initialize the axes. Use pyqtgraph's autoDownsample property instead of the original DispCtrl C function
        Ref: https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html
        '''
        #initializ the display axes
        h = axes.plot([0],[0],pen=pg.mkPen(width=2, color=color),autoDownsample = True)
        axes.setBackground('w')
        index = int(axes.objectName()[-1]) # index to the axis
        if not self.limsetindex[index]: # if not auto axis
            self.ylim(axes,(-1,1))
        return h
    
    def xlim(self,axes,lim):
        # lim: tuple
        axes.setRange(xRange=lim,padding=0)

    def ylim(self,axes,lim):
        # lim: tuple or mode listed below
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
        D = self.fwindow
        if type(self.aitime) == list: #not self.aitime <- won't work once it becomes np array
            print('waiting for data to be displayed... @update_plot')
            return
        
        # draw the top and middle panels
        if (self.slider0v2p == 0): #show all data if the slider value is 0
            XData01 = self.aitime
            if (self.disp.dispindex[0] <= 1) and (self.menuindex[1] == 's'): #Ch0/1 SQA, top axis
                YData0 = self.PSDofSQA[self.disp.dispindex[0]]
            else:
                YData0 = self.aidata[self.disp.dispindex[0]]

            if (self.disp.dispindex[1] <= 1) and (self.menuindex[2] == 's'): #Ch0/1 SQA, middle axis
                YData1 = self.PSDofSQA[self.disp.dispindex[1]]
            else:
                YData1 = self.aidata[self.disp.dispindex[1]]
        else:
            L = self.aitime.size
            if L >= self.slider0v2p:
                XData01 = self.aitime[L-self.slider0v2p:]
                if (self.disp.dispindex[0] <= 1) and (self.menuindex[1] == 's'): #Ch0/1 SQA, top axis
                    YData0 = self.PSDofSQA[self.disp.dispindex[0]][L-self.slider0v2p:]
                else:
                    YData0 = self.aidata[self.disp.dispindex[0]][L-self.slider0v2p:]

                if (self.disp.dispindex[1] <= 1) and (self.menuindex[2] == 's'): #Ch0/1 SQA, middle axis
                    YData1 = self.PSDofSQA[self.disp.dispindex[1]][L-self.slider0v2p:]
                else:
                    YData1 = self.aidata[self.disp.dispindex[1]][L-self.slider0v2p:]
            else:
                XData01 = self.aitime
                if (self.disp.dispindex[0] <= 1) and (self.menuindex[1] == 's'): #Ch0/1 SQA, top axis
                    YData0 = self.PSDofSQA[self.disp.dispindex[0]]
                else:
                    YData0 = self.aidata[self.disp.dispindex[0]]

                if (self.disp.dispindex[1] <= 1) and (self.menuindex[2] == 's'): #Ch0/1 SQA, middle axis
                    YData1 = self.PSDofSQA[self.disp.dispindex[1]]
                else:
                    YData1 = self.aidata[self.disp.dispindex[1]]

        # draw the bottom panel
        if (self.slider1v2p): #show all data if the slider value is 0
            XData2 = self.aitime
            if (self.disp.dispindex[2] <= 1) and (self.menuindex[3] == 's'): #Ch0/1 SQA
                YData2 = self.PSDofSQA[self.disp.dispindex[2]]
            else:
                YData2 = self.aidata[self.disp.dispindex[2]]
        else:
            L = self.aitime.size
            if L >= self.slider1v2p:
                XData2 = self.aitime[L-self.slider1v2p:]
                if (self.disp.dispindex[2] <= 1) and (self.menuindex[3] == 's'): #Ch0/1 SQA
                    YData2 = self.PSDofSQA[self.disp.dispindex[2]][L-self.slider1v2p:]
                else:
                    YData2 = self.aidata[self.disp.dispindex[2]][L-self.slider1v2p:]

            else:
                XData2 = self.aitime
                if (self.disp.dispindex[2] <= 1) and (self.menuindex[3] == 's'): #Ch0/1 SQA
                    YData2 = self.PSDofSQA[self.disp.dispindex[2]]
                else:
                    YData2 = self.aidata[self.disp.dispindex[2]]

        #TODO - translate the following
        # if handles.fcheck(1,Cap7_state.disp.dispindex(1,1))
        #     YData1 = Dfilter2(handles.fswitch,YData1,handles.fwindow);
        # end
        # if handles.fcheck(1,Cap7_state.disp.dispindex(1,2))
        #     YData2 = Dfilter2(handles.fswitch,YData2,handles.fwindow);
        # end
        # if handles.fcheck(1,Cap7_state.disp.dispindex(1,3))
        #     YData3 = Dfilter2(handles.fswitch,YData3,handles.fwindow);
        # end
        if self.disp.invertindex[0]:
            YData0 = -YData0
        if self.disp.invertindex[1]:
            YData1 = -YData1
        if self.disp.invertindex[2]:
            YData2 = -YData2

        # XData = list(range(1000))
        # YData1 = self.pseudoDataGenerator(len(XData))
        # YData2 = self.pseudoDataGenerator(len(XData))
        self.plot0.setData(XData01,YData0)
        self.plot1.setData(XData01,YData1)
        self.plot2.setData(XData2,YData2)
        self.xlim(self.axes0,(XData01[0],XData01[-1]))
        self.xlim(self.axes1,(XData01[0],XData01[-1]))
        if self.Lock.isChecked():
            lim1 = self.ylim(self.axes0,'range')
            D = (lim1[1]-lim1[0])/2
            M = (max(YData1)+min(YData1))/2
            self.ylim(self.axes1,((M-D),(M+D)))

    def create_context_axes(self,axes,pos:QPoint):
        #axidx: index to the axes, 0-based
        context_menu = QMenu(self) # create a QMenu

        # create and add items
        act0 = QAction('Ch0(Y) C', self)
        act1 = QAction('Ch1(X) G', self)
        act2 = QAction('Ch2 I', self)
        act3 = QAction('Ch3 Aux', self)
        act4 = QAction('Ch4 Ra', self)
        act5 = QAction('Invert signal', self)

        axidx = int(axes.objectName()[-1])
        for ch,act in enumerate([act0, act1, act2, act3, act4, act5]):
            act.setCheckable(True)
            if ch == self.disp.dispindex[axidx]:
                act.setChecked(True)
            # the following method must be used... if using ch directly -> always points to ch = 4 somehow...
            if ch == 0:
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,0))
            elif ch == 1:
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,1))
            elif ch == 2:
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,2))
            elif ch == 3:
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,3))
            elif ch == 4:
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,4))
            else:
                if self.disp.invertindex[axidx]:
                    act.setChecked(True)
                act.triggered.connect(lambda checked: self.context_invertSignal_Callback(axes,checked))

            context_menu.addAction(act)
            # action_group.addAction(act)
        context_menu.exec(self.sender().mapToGlobal(pos))

    def create_context_axes_b(self,axes,pos:QPoint):
        #axidx: index to the axes, 0-based
        context_menu = QMenu(self) # create a QMenu

        # create and add items
        # create Ch0 submenu
        menu0 = QMenu('Ch0 C', self)
        act00 = QAction('SQA', self)
        act01 = QAction('PSD(Y)', self)
        menu0.addAction(act00)
        menu0.addAction(act01)

        # create Ch1 submenu
        menu1 = QMenu('Ch1 G', self)
        act10 = QAction('SQA', self)
        act11 = QAction('PSD(X)', self)
        menu1.addAction(act10)
        menu1.addAction(act11)
        
        # create Ch2-4 etc.
        act2 = QAction('Ch2 I', self)
        act3 = QAction('Ch3 Aux', self)
        act4 = QAction('Ch4 Ra', self)
        act5 = QAction('Invert signal', self)

        axidx = int(axes.objectName()[-1])

        #add items to the context menu
        context_menu.addMenu(menu0)
        context_menu.addMenu(menu1)
        for act in [act2,act3,act4,act5]:
            context_menu.addAction(act)

        for idx,act in enumerate([act00, act01, act10, act11, act2, act3, act4, act5]):
            act.setCheckable(True)
            if idx <= 3: #act for Ch0, Ch1
                if idx <= 1: #Ch0
                    if self.disp.dispindex[int(axes.objectName()[-1])] == 0: #disp Ch0
                        if (idx == 0) and (self.menuindex[int(axes.objectName()[-1])+1] == 's'): #Ch0-SQA
                            act.setChecked(True)
                        elif (idx == 1) and (self.menuindex[int(axes.objectName()[-1])+1] == 'p'): #Ch0-PSD
                            act.setChecked(True)
                else: #disp Ch1
                    if self.disp.dispindex[int(axes.objectName()[-1])] == 1: #disp Ch1
                        if (idx == 2) and (self.menuindex[int(axes.objectName()[-1])+1] == 's'): #Ch0-SQA
                            act.setChecked(True)
                        elif (idx == 3) and (self.menuindex[int(axes.objectName()[-1])+1] == 'p'): #Ch0-PSD
                            act.setChecked(True)
                # if idx%2: #PSD
                #     act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,int(idx/2),'p'))
                # else: #SQA
                #     act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,int(idx/2),'s'))
            else: #Ch2-4
                if self.disp.dispindex[int(axes.objectName()[-1])] == (idx-2):
                    act.setChecked(True)
                # act.triggered.connect(lambda checked: self.context_axes_Callback(axes,idx-2))

            if idx == 0:   #Ch0sqa
                act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,0,'s'))
            elif idx == 1: #Ch0psd
                act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,0,'p'))
            elif idx == 2: #Ch1sqa
                act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,1,'s'))
            elif idx == 3: #Ch1psd
                act.triggered.connect(lambda checked: self.context_axes_b_Callback(axes,1,'p'))
            elif idx == 4: #Ch2
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,2))
            elif idx == 5: #Ch3
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,3))
            elif idx == 6: #Ch4
                act.triggered.connect(lambda checked: self.context_axes_Callback(axes,4))
            else:          #Invert signal
                if self.disp.invertindex[axidx]:
                    act.setChecked(True)
                act.triggered.connect(lambda checked: self.context_invertSignal_Callback(axes,checked))
        
        context_menu.exec(self.sender().mapToGlobal(pos))

    def MenuSwitcher(self,type):
        self.menuindex[0] = type
        if type == 1: #SQA
            self.axes0.customContextMenuRequested.connect(lambda pos: self.create_context_axes_b(self.axes0,pos)) #connect to custom context menu
            self.axes1.customContextMenuRequested.connect(lambda pos: self.create_context_axes_b(self.axes1,pos)) #connect to custom context menu
            self.axes2.customContextMenuRequested.connect(lambda pos: self.create_context_axes_b(self.axes2,pos)) #connect to custom context menu
            #TODO - translate the following
            # if (handles.shiftswitch == 1)
            #     contextS_Gsqa_Callback(handles.contextS_Gsqa,[],handles);
            # elseif (handles.shiftswitch == 0)
            #     contextS_Csqa_Callback(handles.contextS_Csqa,[],handles);
            # else
            #     contextS_GCsqa_Callback(handles.contextS_GCsqa,[],handles);
            # end
        else: #PSD
            self.axes0.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes0,pos)) #connect to custom context menu
            self.axes1.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes1,pos)) #connect to custom context menu
            self.axes2.customContextMenuRequested.connect(lambda pos: self.create_context_axes(self.axes2,pos)) #connect to custom context menu
            #TODO - translate the following
            #set(handles.PhaseShift,'UIContextMenu',[]);
            self.menuindex[1:] = 'p'*3 #[0,'p','p','p']

        for axidx,ax in enumerate([self.axes0,self.axes1,self.axes2]): #this will update displayed channels
            self.context_axes_Callback(ax,self.disp.dispindex[axidx])


    def process_data(self,*args):
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
            self.PSDofSQA = np.hstack((self.PSDofSQA,np.vstack((PSD2,PSD1))))

        elif self.algorithm == 1: #PSD
            Time,Cap,Cond,Curr,AICh2 = self.CapEngine(1)
            Ra = np.empty_like(Time)
            Ra.fill(np.nan)
        else: #Hardware
            Time,Cap,Cond,Curr = self.CapEngine(0)

        self.aitime = np.concatenate((self.aitime,Time))
        if self.algorithm == 0:
            if type(self.aidata) == list: #not self.aidata: #no data yet
                self.aidata = np.vstack((Cap,Cond,Curr))
            else:
                self.aidata = np.hstack((self.aidata,np.vstack((Cap,Cond,Curr))))
        else:
            if type(self.aidata) == list: #not self.aidata: #no data yet
                self.aidata = np.vstack((Cap,Cond,Curr,AICh2,Ra))
            else:
                self.aidata = np.hstack((self.aidata,np.vstack((Cap,Cond,Curr,AICh2,Ra))))
        #TODO - paused 1/29/2025, check if the dimension for hstack matches

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
        ppch = int(self.timebuffer.size/self.samplesPerTp) #points per channel
        TIME = np.empty(ppch,dtype=np.float64)
        CAP = np.empty(ppch,dtype=np.float64)
        COND = np.empty(ppch,dtype=np.float64)
        CURR = np.empty(ppch,dtype=np.float64)

        self.lib.Dfilter(0,self.timebuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            int(self.samplesPerTp),int(self.filterv2p),ppch,
            TIME.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        
        if algorithm == 0: #Hardware
            self.lib.Dfilter(int(self.fcheck['rf0']),self.databuffer[0,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.samplesPerTp),int(self.filterv2p),ppch,
                CAP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf1']),self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.samplesPerTp),int(self.filterv2p),ppch,
                COND.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf2']),self.databuffer[2,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.samplesPerTp),int(self.filterv2p),ppch,
                CURR.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))

            return TIME,CAP,COND,CURR

        else: #PSD, SQA
            AICH2 = np.empty(ppch,dtype=np.float64)
            self.lib.Dfilter(int(self.fcheck['rf1']),self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.samplesPerTp),int(self.filterv2p),ppch,
                CURR.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.Dfilter(int(self.fcheck['rf2']),self.databuffer[2,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                int(self.samplesPerTp),int(self.filterv2p),ppch,
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
                        int(self.samplesPerTp),float(taufactor),int(endadj),ppch,
                        ASYMP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        PEAK.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        TAU.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
                else: #Q-SQA
                    interval = (self.timebuffer[self.samplesPerTp-1] - self.timebuffer[0]) / (self.samplesPerTp - 1) #calculate time interval between data points
                    self.lib.SqQ(self.databuffer[0,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        self.timebuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        int(self.samplesPerTp),float(taufactor),int(endadj),ppch,float(interval),
                        ASYMP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        PEAK.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        TAU.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            #also do PSD even the SQA is selected
            self.lib.PSD(self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                self.PSD90.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                Nref,int(self.samplesPerTp),ppch,
                CAP.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
            self.lib.PSD(self.databuffer[1,:].ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                self.PSDref.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                Nref,int(self.samplesPerTp),ppch,
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

            if (0.0005/self.PSDfreq) > (meantau*taufactor): #higher freq is better
                #newfreq = self.PSDfreq-0.2 #move 0.2kHz gradually
                newfreq = 0.001/(meantau*taufactor*2) #in kHz
                if newfreq < (self.rSR*2/1000):
                    newfreq = self.rSR*2/1000
                elif newfreq > 10:
                    newfreq = 10

            if (newfreq != self.PSDfreq) or (newamp != self.PSDamp):
                data, PSDfreq, PSDamp = self.Wavecalc(newfreq,newamp)
                if (abs(PSDfreq-self.PSDfreq)>0.1) or (abs(PSDamp-self.PSDamp)>5):
                    self.aodata = data
                    self.PSDfreq = PSDfreq
                    self.PSDamp = PSDamp
                    self.PSDlog.append([self.aitime[-1],self.PSDfreq,self.PSDamp,
                        self.PSDphase,self.Cm.currentText()]) #[[time,kHz,mV,degree,algorithm],...]
                    self.PSD_freq.setText(f'{self.PSDfreq:.2f}')
                    self.PSD_amp.setText(f'{self.PSDamp:.2f}')
                    self.daq.ao.stop()
                    self.daq.ao.putdata(self.aodata)
                    self.daq.ao.start()
        output = [Cap,Cond,Ra]

    def AIwaiting(self):
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
        L = int((self.samplesPerTp//PPS)*PPS) #make sure that the DC noise can be cancled
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
        #triggerpt = 10
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
        trigsig[0:triggerpt] = 4 #1V is not enough to trigger MCC board...
        output = np.vstack((trigsig,output))
        
        amp = A*abs(self.daqdefault.aoExtConvert); #in mV
        return output,freq,amp
    
    #%% Callbacks -------------------------------------------------------
    def Start_Stop_Callback(self):
        if self.Start_Stop.isChecked(): #start
            #TODO - translate below
            # if Cap7_state.changed
            #     if ~dlg_SaveData(handles.figure1) %canceled or no selection
            #         set(hObject,'Value',0);
            #         return
            #     end
            # end
            self.rSR = abs(float(self.RecordSampleRate.text()))
            if self.rSR > 100:
                self.rSR = 100
                self.RecordSampleRate.setText(str(self.rSR))
            elif self.rSR < 5:
                self.rSR = 5
                self.RecordSampleRate.setText(str(self.rSR))
            self.PSDamp = [] #make it empty in order to enter the 'if' codes in @Set_PSD_Callback
            self.PSDfreq = float(self.PSD_freq.text()) #kHz
            self.PSDphase = float(self.PSD_phase.text()) #degree

            # adjust AI properties
            #self.daq.ai.samplesPerTrig = int(((1/self.rSR)-0.001)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
            self.SpmCount = self.samplesPerTp*round(self.rSR*0.5) # process data every 0.5 sec
            self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
            self.daq.ai.trigFcn = lambda eventdata: self.AIwaiting()
            
            self.filterv2p = round((float(self.filterset.text())/1000)*self.daq.ai.sampleRate) #points to be averaged
            self.fwindow = abs(int(self.filterset2.text())) #samples for the moving filter
            filtermaxp = self.samplesPerTp #calculate maximal averaging points
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
            self.slider0.setValue(0)
            self.slider0v2p = round(self.slider0.value()*self.rSR) #for @update_plot, @slider0_Callback
            self.slider1v2p = round(self.slider1.value()*self.rSR) #for @update_plot, @slider1_Callback
            #TODO - translate below
            # set(handles.xlim1,'String','0');
            # set(handles.xlim2,'String','0');
            # set(handles.figure1,'Name',handles.version.Shell);
            # set(Cap7_gh.NotePad.figure1,'Name',handles.version.Shell);
            # delete(findobj('parent',handles.axes0,'Type','text'));
            # delete(findobj('parent',handles.axes1,'Type','text'));
            # set(handles.group_stop(1,:),'Enable','off');
            # set(handles.group_start(1,:),'Enable','on');
            self.Start_Stop.setText('Waiting')
            self.Start_Stop.setStyleSheet('color:rgb(225,135,0)')

            #adjust AO property
            if self.daq.ao.isrunning:
                self.daq.ao.stop()
            
            self.daq.ao.stop() #might be started again @resume
            sleep(0.003)
            if (self.algorithm >= 2) and (self.menuindex == 0): #SQA but PSD context menu
                self.MenuSwitcher(1) #SQA context menu
            elif (self.algorithm == 1) and (self.menuindex == 1): #PSD but SQA context menu
                self.MenuSwitcher(0) #PSD context menu
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

            self.disptimer.start()
        else: #stop
            self.daq.ai.stop()
            self.daq.ao.stop()
            self.disptimer.stop()
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
            if type(self.aidata) == list:
                return
            else:
                pass
                #TODO - translate below
                # edit_Kseal_Callback(handles.edit_Kseal, eventdata, guidata(gcf)); %TW141015
                # %Show_update_Callback(hObject, eventdata, handles); %will be evoked in
                # %edit_Kseal_Callback %TW141023
            #self.disptimer.stop()

    def context_axes_Callback(self,axes,channel):
        '''
        for selecting display channels
        axidx: index to the axes, 0-based
        channel: the channel being clicked/selected
        '''
        axidx = int(axes.objectName()[-1])
        self.disp.dispindex[axidx] = channel
        #print(f'axes {axidx}, {channel}')
        if axidx == 0:
            plotx = self.plot0
        elif axidx == 1:
            plotx = self.plot1
        else:
            plotx = self.plot2
        
        #update plot color
        plotx.setPen(pg.mkPen(width=2, color=self.disp.chcolor[channel]))
        #TODO - translate the following
        # if strcmpi(handles.ai.running,'off') && (~isempty(handles.aitime))
        #     Show_update_Callback(hObject, eventdata, handles);
        # end

    def context_axes_b_Callback(self,axes,channel,algo):
        '''
        for selecting display channels (Ch0 and Ch1 only)
        axidx: index to the axes, 0-based
        channel: the channel being clicked/selected
        algo: show PSD('p') or SQA('s') data for Ch0/1
        '''
        #print(f'ch:{channel}, algo:{algo}')
        self.menuindex[int(axes.objectName()[-1])+1] = algo
        self.context_axes_Callback(axes,channel)

    def context_invertSignal_Callback(self,axes,checked):
        '''
        invert the polarity of the signal of a given axis or not
        '''
        self.disp.invertindex[int(axes.objectName()[-1])] = checked #[top, middle, bottom]
        #TODO - translate the following
        # if strcmpi(handles.ai.running,'off') && (~isempty(handles.aitime))
        #     Show_update_Callback(hObject, eventdata, handles);
        # end

    def AxesSwitch_Callback(self):
        self.limsetindex[0] = self.AxesSwitch.currentIndex()
        self.Auto_axes.setChecked(self.limsetindex[0]+1)
        
    def Set_ylim_Callback(self):
        if self.limsetindex[0] == 0:
            axes = self.axes0
        elif self.limsetindex[0] == 1:
            axes = self.axes1
        else:
            axes = self.axes2
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
            axes = self.axes0
        elif self.limsetindex[0] == 1:
            axes = self.axes1
        else:
            axes = self.axes2
        
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
            axes = self.axes0
        elif self.limsetindex[0] == 1:
            axes = self.axes1
        else:
            axes = self.axes2
        
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
            if (self.limsetindex[0] == 1) and (self.limsetindex[2] == False): #Mark auto-axis if it's axes1
                self.Auto_axes.setChecked(True)
            self.limsetindex[2] = True
        else:
            self.ylim(self.axes1,'auto')

    def slider_Callback(self):
        value = self.sender().value() #int
        if self.sender().objectName() == 'slider0': #slider0 or slider1
            self.slider0v2p = round(value*self.rSR)
            self.text_slider0.setText(str(value))
        else: #slider1
            self.slider1v2p = round(value*self.rSR)
            self.text_slider1.setText(str(value))
        #TODO - remaining display control code
        #Note - Page change won't emit sliderReleased() signal. i.e. cannot put disp update code in the corresponding callback

    def Show_Callback(self):
        #TODO - paused 1/29/2025
        pass
    
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
            self.PSD_freq.setText(f'{self.PSDfreq:.2f}')
            self.PSD_amp.setText(f'{self.PSDamp:.2f}')
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
            #TODO - translate below
            # %---adjust filter setting automatically
            # filtermaxp = handles.aiSamplesPerTrigger; %calculate maximal averaging points
            # filterp = round(abs((str2double(get(handles.filterset,'String'))/1000)*Cap7_state.daq.aiSR));
            # handles.filterv2p = FilterCalc(filterp,filtermaxp,Cap7_state.daq.aiSR,handles.PSDfreq);
            # if (handles.filterv2p == 1)
            #     set(handles.filterset,'String','0');
            # else
            #     set(handles.filterset,'String',num2str(1000*handles.filterv2p/Cap7_state.daq.aiSR));
            # end
           
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
        filtermaxp = self.samplesPerTp #calculate maximal averaging points
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
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
