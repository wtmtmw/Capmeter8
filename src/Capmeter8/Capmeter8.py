from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMenu, QToolBar, QStyle, QSizePolicy #, QVBoxLayout, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import QTimer, QPoint, QSize, QEventLoop
from PyQt6.QtGui import QAction, QFont #, QKeySequence
import qtawesome as qta # for FontAwesome icon
from tkinter import filedialog, Tk, messagebox
# from pyqtgraph import PlotWidget, plot #for packaging only if loading .ui directly? need to test...
import sys, traceback, ctypes, time
import pyqtgraph as pg # for real-time plotting
import matplotlib.pyplot as plt # for generating figures
from pathlib import Path
import numpy as np
import pandas as pd
from math import ceil
from random import randint
from daqx.util import createDevice

class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        '''
        Set up variables
        '''
        self.appdir = Path(__file__).parent
        self.shell = 'Capmeter8 v0.0.0'
        
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
                                   chcolor = [(255,0,0),(0,0,255),(204,0,204),(64,153,166),(0,0,0)], #display color of the channel
                                   slider0range = 120, # in sec
                                   slider1range = 50, # in sec
                                   invertindex = [False,False,False], #[axes0,axes1,axes2]
                                   )
        
        self.gh = self.kwarg2var(notePad = None,
                                 dataTable = None,
                                 crosshair = None) #TODO - Cap7_gh has not been implemented

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
        self.setWindowTitle(self.shell)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMenuButton))
        self.toolbar = self.create_toolbar()
        self.menuindex = [0,'p','p','p'] # [context menu ID, axes0 PSD or SQA, axes1 PSD or SQA, axes2 PSD or SQA], modified in @MenuSwitcher
        # context menu ID: 0-normal, 1-PSDofSQA; displayed data 'p'-PSD, 's'-SQA
        self.limsetindex = [self.AxesSwitch.currentIndex(),True,True,True]; #[axis #,Auto,Auto,Auto], axes is 0-based
        self.Auto_axes.setChecked(self.limsetindex[self.limsetindex[0]+1])

        self.plot0 = self.iniAxes(self.axes0,self.disp.chcolor[self.disp.dispindex[0]])
        self.plot1 = self.iniAxes(self.axes1,self.disp.chcolor[self.disp.dispindex[1]])
        self.plot2 = self.iniAxes(self.axes2,self.disp.chcolor[self.disp.dispindex[2]])

        self.labelindex = [] #[dispindex,time,data,'string'] 0-based
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
        self.aidata = np.array([]) # np.ndarray; M-by-Timepoint matrix, where M is the number of parameters/channels
        self.aidata2 = [] # Kseal adjusted data
        self.aodata = []
        self.aitime = np.array([])
        self.starttime = -1 #negative value for initialization; time of the first AI trigger
        self.timeoffset = 0 #AI may be restarted by Set_PSD_Callback. This offset is needed to make aitime continuous
        self.PSDofSQA = np.array([])
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
        self.lib.Dfilter2.restype = None
        self.lib.Dfilter2.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self.lib.PSD.restype = None
        self.lib.PSD.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self.lib.SqCF.restype = None
        self.lib.SqCF.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
        self.lib.SqQ.restype = None
        self.lib.SqQ.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
        self.lib.SqWaveCalc.restype = None
        self.lib.SqWaveCalc.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
        
        #%%
        '''
        Set up AO and AI
        '''
        # create device and AO
        try:
            self.daq = createDevice('mcc',self.daqdefault.daqid)
            self.daq.eventlistener.timer._dt = 0.005 #default was 0.0001. Adjust according to CPU speed
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
        self.slider0.setMaximum(int(self.disp.slider0range*self.rSR))
        self.slider0.setSingleStep(ceil(self.rSR)) # 1 sec
        self.slider0.setPageStep(ceil(10*self.rSR)) #10 sec
        self.slider0.setTickInterval(ceil(10*self.rSR))
        self.text_slider0.setText(f'{self.slider0.value()/self.rSR:.0f}')
        self.slider1.setMaximum(int(self.disp.slider1range*self.rSR))
        self.slider1.setSingleStep(ceil(self.rSR)) # 1 sec
        self.slider1.setPageStep(ceil(10*self.rSR)) #10 sec
        self.slider1.setTickInterval(ceil(10*self.rSR))
        self.text_slider1.setText(f'{self.slider1.value()/self.rSR:.0f}')
        self.slider0v2p = self.slider0.value() #for @update_plot, @slider0_Callback
        self.slider1v2p = self.slider1.value() #for @update_plot, @slider1_Callback
        self.filterv2p = round((float(self.filterset.text())/1000)*self.daq.ai.sampleRate) #points to be averaged
        
        self.SpmCount = self.samplesPerTp*round(self.rSR*0.5) # process data every 0.5 sec
        self.databuffer = [] # for @process_data
        self.timebuffer = [] # for @process_data
        
        # setup Callbacks
        self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
        self.daq.ai.samplesAcquiredFcn = lambda eventdata: self.process_data()
        self.daq.ai.trigFcn = lambda eventdata: self.AIwaiting(eventdata)
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

        self.ChangedOrSaved()


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
        self.xlim0.returnPressed.connect(self.Show_update_Callback)
        self.xlim1.returnPressed.connect(self.Show_update_Callback)
        self.Show_to.clicked.connect(self.Show_to_Callback)
        self.makeFig.clicked.connect(self.makeFig_Callback)
        self.toClipboard.clicked.connect(self.toClipboard_Callback)
        self.Std_get.clicked.connect(self.Std_get_Callback)
        self.Std_scale.clicked.connect(self.Std_scale_Callback)

        self.Set_PSD.clicked.connect(self.Set_PSD_Callback)
        self.PhaseShift.clicked.connect(self.PhaseShift_Callback)
        self.PSDadd90.clicked.connect(self.PSDadd90_Callback)
        self.AutoPhase.clicked.connect(self.AutoPhase_Callback)
        self.PSD_slider.valueChanged.connect(self.PSD_slider_Callback) #for updating PSD_phase edit box
        self.PSD_slider.sliderReleased.connect(self.Set_PSD_Callback) #set PSD only when the slider is released
        # self.PSD_slider.sliderPressed.connect(lambda : print('sliderPressed')) #valueChanged somehow is ahead of sliderPressed
        # self.PSD_slider.valueChanged.connect(lambda v: print(f'valueChanged {v}'))
        # self.PSD_slider.sliderMoved.connect(lambda v: print(f'sliderMoved {v}')) #sliderMoved execution is ahead of valueChanged
        # self.PSD_slider.sliderReleased.connect(lambda : print('sliderReleased'))
        self.Cm.currentIndexChanged.connect(self.Cm_Callback)
        self.Auto_FP.stateChanged.connect(self.Auto_FP_Callback)

        for key in self.fcheck.keys():
            exec(f'self.{key}.stateChanged.connect(self.FilterCheck_Callback)')
        self.Set_filter.clicked.connect(self.Set_filter_Callback)
        self.Set_filter2.clicked.connect(self.Set_filter2_Callback)
        self.FilterSwitch.currentIndexChanged.connect(self.FilterSwitch_Callback)

        for n in range(10): #connect to callback and set shortcut setShortcut("F1")
            exec(f'self.labelButton_{n}.clicked.connect(self.LabelButton_Callback)')
            if n == 0:
                self.labelButton_0.setShortcut("F10")
            else:
                exec(f'self.labelButton_{n}.setShortcut("F{n}")')

        #%%
        '''
        Other GUI setting
        '''
        #self.PSD_phase.setTextMargins(QMargins(0,0,0,0)) #zero already...
        #print(self.PSD_phase.textMargins().left())
        # Set up context menu
        # Note - cannot connect context menu callback using the loop below. The default channel will be wrong (Ch4-Ra for all axes)...
        for ax in [self.axes0,self.axes1,self.axes2]:
            ax.getPlotItem().setMenuEnabled(False) #disable default pyqtplot context menu
            #ax.customContextMenuRequested.connect(lambda pos,axis=ax: self.create_context_axes(axis,pos)) #connect to custom context menu
        
        #adjust displayed channel and connect to callbacks
        if self.algorithm >= 2:
            self.MenuSwitcher(1) #SQA
        else:
            self.MenuSwitcher(0) #PSD

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

    class crosshair:
        def __init__(self, ax):
            self.ax = ax
            self.v_line = pg.InfiniteLine(angle=90, movable=False)
            self.h_line = pg.InfiniteLine(angle=0, movable=False)
            self.ax.addItem(self.v_line, ignoreBounds=True)
            self.ax.addItem(self.h_line, ignoreBounds=True)
            self.proxy = pg.SignalProxy(self.ax.scene().sigMouseMoved, rateLimit=180, slot=self.mouse_moved)

        def __del__(self):
            self.ax.removeItem(self.v_line)
            self.ax.removeItem(self.h_line)

        def mouse_moved(self, evt):
            pos = evt[0]  # Get the mouse position
            if self.ax.sceneBoundingRect().contains(pos):
                mouse_point = self.ax.plotItem.vb.mapSceneToView(pos)
                self.v_line.setPos(mouse_point.x())
                self.h_line.setPos(mouse_point.y())

    def uigetfile(self,**kargs):
        '''
        **kargs include:
        parent - the window to place the dialog on top of
        title - the title of the window
        initialdir - the directory that the dialog starts in
        initialfile - the file selected upon opening of the dialog
        filetypes - a sequence of (label, pattern) tuples, ‘*’ wildcard is allowed
        defaultextension - default extension to append to file (save dialogs)
        multiple - when true, selection of multiple items is allowed
        Ref: https://docs.python.org/3/library/dialog.html#module-tkinter.filedialog
        Ref: https://realpython.com/python-pathlib/
        '''
        root = Tk()
        root.attributes('-topmost',True)
        root.withdraw()
        file = filedialog.askopenfilename(**kargs)
        root.destroy()
        return Path(file)

    def uisavefile(self,**kargs):
        '''
        **kargs include:
        parent - the window to place the dialog on top of
        title - the title of the window
        initialdir - the directory that the dialog starts in
        initialfile - the file selected upon opening of the dialog
        filetypes - a list of (label, pattern) tuples, ‘*’ wildcard is allowed
        defaultextension - default extension to append to file (save dialogs)
        multiple - when true, selection of multiple items is allowed
        Ref: https://docs.python.org/3/library/dialog.html#module-tkinter.filedialog
        Ref: https://realpython.com/python-pathlib/
        '''
        root = Tk()
        root.attributes('-topmost',True)
        root.withdraw()
        file = filedialog.asksaveasfilename(**kargs)
        root.destroy()
        return Path(file)

    def iniAxes(self,axes,color):
        '''
        Initialize the axes. Use pyqtgraph's autoDownsample property instead of the original DispCtrl C function
        Ref: https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html
        '''
        #initializ the display axes
        h = axes.plot([0],[0],pen=pg.mkPen(width=2, color=color),autoDownsample = True)
        axes.setBackground('w')
        index = int(axes.objectName()[-1]) # index to the axis
        if self.limsetindex[index+1]: # if not auto axis
            self.ylim(axes,'auto')
        else:
            self.ylim(axes,(-1,1))
        return h
    
    def xlim(self,axes,lim):
        # lim: tuple or mode listed below
        if lim == 'auto':
            axes.getViewBox().enableAutoRange(axis='x')
        elif lim == 'manual':
            axes.getViewBox().disableAutoRange(axis='x')
        elif lim == 'range': #get current range
            return axes.getViewBox().viewRange()[0] # [[x0,x1],[y0,y1]]
        else:
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
        if self.aitime.size == 0: #not self.aitime <- won't work once it becomes np array
            print('waiting for data to be displayed... @update_plot')
            return
        
        # draw the top and middle panels
        if (self.slider0v2p == 0): #show all data if the slider value is 0
            XData01 = self.aitime
            if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[1] == 'p'): #Ch0/1 PSDofSQA, top axis
                YData0 = self.PSDofSQA[self.disp.dispindex[0]]+0 # +0 forces Python to make a hard copy of the data
            else:
                YData0 = self.aidata[self.disp.dispindex[0]]+0

            if (self.disp.dispindex[1] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[2] == 'p'): #Ch0/1 PSDofSQA, middle axis
                YData1 = self.PSDofSQA[self.disp.dispindex[1]]+0
            else:
                YData1 = self.aidata[self.disp.dispindex[1]]+0
        else:
            L = self.aitime.size
            if L >= self.slider0v2p:
                XData01 = self.aitime[L-self.slider0v2p:]
                if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[1] == 'p'): #Ch0/1 PSDofSQA, top axis
                    YData0 = self.PSDofSQA[self.disp.dispindex[0],L-self.slider0v2p:]+0
                else:
                    YData0 = self.aidata[self.disp.dispindex[0],L-self.slider0v2p:]+0

                if (self.disp.dispindex[1] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[2] == 'p'): #Ch0/1 PSDofSQA, middle axis
                    YData1 = self.PSDofSQA[self.disp.dispindex[1],L-self.slider0v2p:]+0
                else:
                    YData1 = self.aidata[self.disp.dispindex[1],L-self.slider0v2p:]+0
            else:
                XData01 = self.aitime
                if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[1] == 'p'): #Ch0/1 PSDofSQA, top axis
                    YData0 = self.PSDofSQA[self.disp.dispindex[0]]+0
                else:
                    YData0 = self.aidata[self.disp.dispindex[0]]+0

                if (self.disp.dispindex[1] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[2] == 'p'): #Ch0/1 PSDofSQA, middle axis
                    YData1 = self.PSDofSQA[self.disp.dispindex[1]]+0
                else:
                    YData1 = self.aidata[self.disp.dispindex[1]]+0

        # draw the bottom panel
        if (self.slider1v2p == 0): #show all data if the slider value is 0
            XData2 = self.aitime
            if (self.disp.dispindex[2] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[3] == 'p'): #Ch0/1 PSDofSQA
                YData2 = self.PSDofSQA[self.disp.dispindex[2]]+0
            else:
                YData2 = self.aidata[self.disp.dispindex[2]]+0
        else:
            L = self.aitime.size
            if L >= self.slider1v2p:
                XData2 = self.aitime[L-self.slider1v2p:]
                if (self.disp.dispindex[2] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[3] == 'p'): #Ch0/1 PSDofSQA
                    YData2 = self.PSDofSQA[self.disp.dispindex[2],L-self.slider1v2p:]+0
                else:
                    YData2 = self.aidata[self.disp.dispindex[2],L-self.slider1v2p:]+0

            else:
                XData2 = self.aitime
                if (self.disp.dispindex[2] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[3] == 'p'): #Ch0/1 PSDofSQA
                    YData2 = self.PSDofSQA[self.disp.dispindex[2]]+0
                else:
                    YData2 = self.aidata[self.disp.dispindex[2]]+0
        # XData = list(range(1000))
        # YData1 = self.pseudoDataGenerator(len(XData))
        # YData2 = self.pseudoDataGenerator(len(XData))

        self.refresh_plot(XData01,YData0,YData1,XData2,YData2)

    def refresh_plot(self,XData01,YData0,YData1,XData2,YData2):
        '''
        Refresh data displayed on the plots. Called by self.update_plot and self.Show_update_Callback
        Note: YData of len() == 0 (e.g. []) will be skipped
        Note: YData0 and YData1 must be updated together
        Note: this function does not handle labels
        '''
        # void Dfilter2(int fswitch, double *data, int W, int wswitch, int M, double *output)
        # fswitch 0:bypass,1:mean,2:median
        # wswitch -1:left,0:center,1:right (window position relative to the time point)
        for idx,ydata in enumerate([YData0,YData1,YData2]): # modify in-place
            if len(ydata) > 0: # have something to update
                if self.fcheck[f'mf{self.disp.dispindex[idx]}']:
                    self.lib.Dfilter2(self.fswitch,ydata.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                                    self.fwindow,0,ydata.size,
                                    ydata.ctypes.data_as(ctypes.POINTER(ctypes.c_double))) #modify in place
                if self.disp.invertindex[idx]:
                    ydata[:] *= -1 #this is in-place modificaton using [:] assignment

        # XData = list(range(1000))
        # YData1 = self.pseudoDataGenerator(len(XData))
        # YData2 = self.pseudoDataGenerator(len(XData))
        try:
            if len(XData01) > 0: # set axes0 and 1
                self.plot0.setData(XData01,YData0)
                self.plot1.setData(XData01,YData1)
                self.xlim(self.axes0,(XData01[0],XData01[-1]))
                self.xlim(self.axes1,(XData01[0],XData01[-1]))
                if self.Lock.isChecked():
                    lim1 = self.ylim(self.axes0,'range')
                    D = (lim1[1]-lim1[0])/2
                    M = (max(YData1)+min(YData1))/2
                    self.ylim(self.axes1,((M-D),(M+D)))

            if len(XData2) > 0:
                self.plot2.setData(XData2,YData2)
                self.xlim(self.axes2,(XData2[0],XData2[-1]))
        except:
            print(XData01.shape)
            print(YData0.shape)
            print(YData1.shape)
            print(XData2.shape)
            print(YData2.shape)
        
    def create_toolbar(self):
        '''
        Ref: https://www.pythonguis.com/tutorials/pyqt-actions-toolbars-menus/
             https://www.pythonguis.com/faq/built-in-qicons-pyqt/
             https://github.com/spyder-ide/qtawesome
             https://fontawesome.com/search?ic=free
        '''
        # Create a Toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(16,16))
        self.addToolBar(toolbar)
        
        # Get Standard Icon
        save_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        load_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        note_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)

        # Create Action
        sep = False #False will actually add a separator
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) #push the setting icon to the right side of the toolbar
        saveact = QAction(save_icon, "Save", self)
        saveact.setShortcut("Ctrl+S")  # Add Shortcut
        toolbar.saveact = saveact #create a reference so it can be modified by other methods
        loadact = QAction(load_icon, "Open", self)
        loadact.setShortcut("Ctrl+O")  # Add Shortcut
        toolbar.loadact = loadact #create a reference so it can be modified by other methods
        noteact = QAction(note_icon, "Notepad", self)
        noteact.setShortcut("Ctrl+N")  # Add Shortcut
        toolbar.noteact = noteact #create a reference so it can be modified by other methods
        setact = QAction(qta.icon('fa5s.cog'),'Setting',self)
        #setact = QAction(qta.icon('fa5s.ellipsis-h'),'Setting',self)
        toolbar.setact = setact #create a reference so it can be modified by other methods

        # Connect to Callback
        saveact.triggered.connect(self.Save_Callback)
        loadact.triggered.connect(self.Load_Callback)
        noteact.triggered.connect(self.Notepad_Callback)
        setact.triggered.connect(self.Setting_Callback)

        # Disable buttons that have not been implemented yet
        noteact.setEnabled(False)
        setact.setEnabled(False)

        # Add Action to Toolbar
        for act in [saveact,loadact,sep,noteact,spacer,setact]:
            if act:
                if isinstance(act,QAction):
                    toolbar.addAction(act)
                else:
                    toolbar.addWidget(spacer)
            else:
                toolbar.addSeparator()

        return toolbar

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
                #print(f'axes{axidx} ch{ch} checked')
                act.setChecked(True)
            if ch <= 4:
                act.triggered.connect(lambda checked,channel=ch: self.context_axes_Callback(axes,channel))
                '''
                channel=ch must be used in lambda otherwise ch will always be 4. The problem arises because
                ch is evaluated lazily when the lambda function is called, not when it is defined. This means
                that by the time any of the lambda functions are executed, ch has already been set to its
                final value in the loop (which is 4 in this case). -insight from ChatGPT...
                '''
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
        menu0 = QMenu(self)
        menu0action = QAction('Ch0 C', self, checkable=True)
        menu0action.setMenu(menu0) #this approach makes the submenu itself checkable
        act00 = QAction('SQA', self)
        act01 = QAction('PSD(Y)', self)
        menu0.addAction(act00)
        menu0.addAction(act01)

        # create Ch1 submenu
        menu1 = QMenu(self) 
        menu1action = QAction('Ch1 G', self, checkable=True)
        menu1action.setMenu(menu1) #this approach makes the submenu itself checkable
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
        context_menu.addAction(menu0action)
        context_menu.addAction(menu1action)
        for act in [act2,act3,act4,act5]:
            context_menu.addAction(act)

        for idx,act in enumerate([act00, act01, act10, act11, act2, act3, act4, act5]):
            act.setCheckable(True)
            if idx <= 3: #act for Ch0, Ch1
                if idx <= 1: #Ch0
                    if self.disp.dispindex[int(axes.objectName()[-1])] == 0: #disp Ch0
                        menu0action.setChecked(True)
                        if (idx == 0) and (self.menuindex[int(axes.objectName()[-1])+1] == 's'): #Ch0-SQA
                            act.setChecked(True)
                        elif (idx == 1) and (self.menuindex[int(axes.objectName()[-1])+1] == 'p'): #Ch0-PSD
                            act.setChecked(True)
                else: #disp Ch1
                    if self.disp.dispindex[int(axes.objectName()[-1])] == 1: #disp Ch1
                        menu1action.setChecked(True)
                        if (idx == 2) and (self.menuindex[int(axes.objectName()[-1])+1] == 's'): #Ch0-SQA
                            act.setChecked(True)
                        elif (idx == 3) and (self.menuindex[int(axes.objectName()[-1])+1] == 'p'): #Ch0-PSD
                            act.setChecked(True)
                if idx%2: #PSD
                    act.triggered.connect(lambda checked,idx=idx: self.context_axes_b_Callback(axes,int(idx/2),'p'))
                else: #SQA
                    act.triggered.connect(lambda checked,idx=idx: self.context_axes_b_Callback(axes,int(idx/2),'s'))
            elif idx == 7: #Invert signal
                if self.disp.invertindex[axidx]:
                    act.setChecked(True)
                act.triggered.connect(lambda checked: self.context_invertSignal_Callback(axes,checked))
            else: #Ch2-4
                if self.disp.dispindex[int(axes.objectName()[-1])] == (idx-2):
                    act.setChecked(True)
                act.triggered.connect(lambda checked,idx=idx: self.context_axes_Callback(axes,idx-2))
        
        context_menu.exec(self.sender().mapToGlobal(pos))

    def MenuSwitcher(self,type):
        self.menuindex[0] = type
        for axidx,ax in enumerate([self.axes0,self.axes1,self.axes2]):
            try:
                ax.customContextMenuRequested.disconnect()
            except: #this happens when no signal is connected yet
                pass
            if type == 1: #SQA
                ax.customContextMenuRequested.connect(lambda pos,axis=ax: self.create_context_axes_b(axis,pos)) #connect to custom context menu
            else: #PSD
                ax.customContextMenuRequested.connect(lambda pos,axis=ax: self.create_context_axes(axis,pos)) #connect to custom context menu

            #self.context_axes_Callback(ax,self.disp.dispindex[axidx]) #this will update displayed channels regardless of PSD or SQA

        if type == 1: #SQA
            self.menuindex[1:] = 's'*3 #[1,'s','s','s']
            #TODO - translate the following
            # if (handles.shiftswitch == 1)
            #     contextS_Gsqa_Callback(handles.contextS_Gsqa,[],handles);
            # elseif (handles.shiftswitch == 0)
            #     contextS_Csqa_Callback(handles.contextS_Csqa,[],handles);
            # else
            #     contextS_GCsqa_Callback(handles.contextS_GCsqa,[],handles);
            # end
        else: #PSD
            self.menuindex[1:] = 'p'*3 #[0,'p','p','p']

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
            if self.PSDofSQA.size == 0: #no data yet
                self.PSDofSQA = np.vstack((PSD2,PSD1))
            else:
                self.PSDofSQA = np.hstack((self.PSDofSQA,np.vstack((PSD2,PSD1))))

        elif self.algorithm == 1: #PSD
            Time,Cap,Cond,Curr,AICh2 = self.CapEngine(1)
            Ra = np.empty_like(Time)
            Ra.fill(np.nan)
        else: #Hardware
            Time,Cap,Cond,Curr = self.CapEngine(0)

        Time += self.timeoffset #AI may be restarted by Set_PSD_Callback. timeoffset is the time difference between the 1st and current triggers
        self.aitime = np.concatenate((self.aitime,Time))
        if self.algorithm == 0:
            if self.aidata.size == 0: #not self.aidata: #no data yet
                self.aidata = np.vstack((Cap,Cond,Curr))
            else:
                self.aidata = np.hstack((self.aidata,np.vstack((Cap,Cond,Curr))))
        else:
            if self.aidata.size == 0: #not self.aidata: #no data yet
                self.aidata = np.vstack((Cap,Cond,Curr,AICh2,Ra))
            else:
                self.aidata = np.hstack((self.aidata,np.vstack((Cap,Cond,Curr,AICh2,Ra))))

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
        return (Cap,Cond,Ra)

    def AIwaiting(self,eventdata):
        '''
        aiTriggerFcn for Start_Stop button
        eventdata is a dict of {'time':event time, 'event':event type}
        '''
        self.Start_Stop.setText('Started')
        self.Start_Stop.setStyleSheet('color:green')
        if self.starttime<0:
            self.starttime = eventdata['time']
        self.timeoffset = eventdata['time'] - self.starttime

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
            L = int(round(L/N)*N); #re-calculate samples per trigger
            freq = self.daq.ao.sampleRate/N/1000; #in kHz
            output = np.empty(L,dtype = np.float64)
            self.lib.SqWaveCalc(int(L),int(N),A,output.ctypes.data_as(ctypes.POINTER(ctypes.c_double))) #modify in-place
        elif self.algorithm ==1: #PSD, produce sine wave
            T = L/self.daq.ao.sampleRate
            P = np.pi/2 #pi/2 shifted, in order to put the trigger at the top -> this seems unnecessary since we use digital trigger now
            cycles = round(freq*1000*(L/self.daq.ao.sampleRate))
            N = L/cycles
            freq = cycles/(L/self.daq.ao.sampleRate)/1000
            output = ((A/2)*np.sin(np.linspace(P,(P+(2*np.pi*freq*1000*T)),L,endpoint=False)))
        else: #Hardware
            output = np.zeros(L)
        
        # trigsig = np.zeros(L) #this is wrong. Intact square wave is needed for locating peak current.
        # trigsig[0:triggerpt] = 4 #1V is not enough to trigger MCC board...
        if self.algorithm <= 1: #Hardware or PSD
            trigsig = np.zeros(L)
            trigsig[0:triggerpt] = 4 #1V is not enough to trigger MCC board...
        else: #SQA
            trigsig = output/(A/8) #+/-4V
        # print(f'output shape:{output.shape}')
        output = np.vstack((trigsig,output))
        
        amp = A*abs(self.daqdefault.aoExtConvert); #in mV
        return output,freq,amp
    
    def indexLoc(self,timeref,pts):
        '''
        get the index(es) closest to the input time point(s)
        timeref: time reference
        pts: query time point(s) in a list e.g. [t1,t2,...,ti]
        [n1,n2,...ni] = indexLoc(timeref,t1,t2,...,ti)
        '''
        return [np.argmin(np.fabs(timeref - t)) for t in pts]
    
    def savevar(self,file):
        '''
        Prepare and save variables. It will be used by manual and auto save functions
        file: pathlib.Path of the target file
        Combining file parts:
        https://stackoverflow.com/questions/61321503/is-there-a-pathlib-alternate-for-os-path-join
        '''
        data = {'DAQinfo':{}} #collect all variables to be saved
        data['DAQinfo']['aiSR'] = self.daq.ai.sampleRate
        data['DAQinfo']['aoSR'] = self.daq.ao.sampleRate
        data['DAQinfo']['aoExtConvert'] = self.daqdefault.aoExtConvert
        data['DAQinfo']['startTime'] = time.ctime(self.starttime)
        data['pulseData'] = self.pulse.data

        #note = deblank(cellstr(get(Cap7_gh.NotePad.edit_note,'String')));
        for var in ['aidata','aitime','labelindex','PSDlog','Pulselog','shell','PSDofSQA']: #collect the rest of variables to be saved
            try:
                data[var] = getattr(self,var)
            except:
                print(f'{var} not saved')
        if file.suffix == '.csv':
            raise NotImplementedError
        elif file.suffix == '.mat':
            raise NotImplementedError
        else:
            savename = file.parent/f'{file.stem}.npy' #ensure the extension is npy
            np.save(savename,data,allow_pickle=True)

    def ChangedOrSaved(self):
        if self.changed:
            self.toolbar.saveact.setEnabled(True)
            self.setWindowTitle(f'{self.shell}*') #add a '*'
        else: #saved
            self.toolbar.saveact.setEnabled(False)
            self.setWindowTitle(self.shell) #remove '*'
            #TODO - translate below
            #set(Cap7_gh.NotePad.figure1,'Name',strtok(get(Cap7_gh.NotePad.figure1,'Name'),'*')); %remove '*'
        #set(Cap7_gh.NotePad.figure1,'Name',get(handles.figure1,'Name'));

    def dlg_SaveData(self):
        '''
        Ref: https://docs.python.org/3/library/tkinter.messagebox.html
            Return True if the answer is yes, None if cancelled, and False otherwise
        '''    
        button = messagebox.askyesnocancel(title='Capmeter8', message='Save data?', default='yes')
        if button: #yes
            self.Save_Callback()
            return True #for if continuing or not
        elif button == False: #no
            return True
        else: #cancel or no selection
            #print('cancel or no selection')
            return False

    def addLabel(self,ax,X,Y,S):
        '''
        e.g. self.addLabel(0,x,y,'text') add label 'text' to self.axes0 at (x,y)
        '''
        axid = int(ax.objectName()[-1])
        text = pg.TextItem(S,color = 'k')
        text.setFont(QFont('Arial',14))
        ax.addItem(text)
        Y = Y[self.disp.dispindex[axid]]
        if np.isnan(Y):
            Y = np.mean(self.ylim(ax,'range'))/2
        text.setPos(X,Y)
        # exec(f'self.axes{axid}.addItem(text)')
        # exec(f'text.setPos(X,Y[self.disp.dispindex[{axid}]])')

    def deleteLabel(self):
        for ax in [self.axes0, self.axes1]:
            for item in ax.items():
                if isinstance(item,pg.TextItem):
                    ax.removeItem(item)

    def ginput(self,ax,npt=1):
        crosshair = self.crosshair(ax)
        ax.scene().sigMouseClicked.connect(lambda event: self.mouseInput(ax,event))
        wait = QEventLoop()
        wait.exec()
        #TODO - paused - not finished - 2/26/2025
        #print(f"Clicked at: x={x:.2f}, y={y:.2f}")

    def mouseInput(self,ax,event):
        # Check if the left mouse button was clicked
        if event.button() == pg.QtCore.Qt.MouseButton.LeftButton:
            # Get the position of the click
            pos = event.scenePos()

            # Check if the click is within the plot area
            if ax.sceneBoundingRect().contains(pos):
                # Map the click position to the view coordinates (data coordinates)
                mouse_point = ax.plotItem.vb.mapSceneToView(pos) #vb means ViewBox
                x = mouse_point.x()
                y = mouse_point.y()

                # Print or display the coordinates
                #print(f"Clicked at: x={x:.2f}, y={y:.2f}")
                return x,y #TODO - paused - may not work - 2/26/2025
        else:
            return ()


    #%% Callbacks -------------------------------------------------------
    def Start_Stop_Callback(self):
        if self.Start_Stop.isChecked(): #start
            #TODO - translate below
            if self.changed:
                if not self.dlg_SaveData(): #canceled or no selection
                    self.Start_Stop.setChecked(False)
                    return
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
            #TODO - change ai.trigType to 'instant' for Hardware mode? may also need to disable the Set_PSD button
            #self.daq.ai.samplesPerTrig = int(((1/self.rSR)-0.001)*self.daqdefault.aiSR) # 100Hz rSR => acquire 9ms data
            self.SpmCount = self.samplesPerTp*round(self.rSR*0.5) # process data every 0.5 sec
            self.daq.ai.samplesAcquiredFcnCount = self.SpmCount
            self.daq.ai.trigFcn = lambda eventdata: self.AIwaiting(eventdata)
            
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
            self.aidata = np.array([])
            self.aitime = np.array([])
            self.starttime = -1 #negative value for initialization
            self.timeoffset = 0 #AI may be restarted by Set_PSD_Callback. This offset is needed to make aitime continuous
            self.PSDofSQA = np.array([])
            self.Pulselog = []
            self.Stdfactor = [] # convert volt to fF
            self.labelindex = []
            self.slider0.setMaximum(int(self.disp.slider0range*self.rSR))
            self.slider0.setValue(0)
            self.slider0.setSingleStep(ceil(self.rSR)) # 1 sec
            self.slider0.setPageStep(ceil(10*self.rSR)) #10 sec
            self.slider0.setTickInterval(ceil(10*self.rSR))

            self.text_slider0.setText(f'{self.slider0.value()/self.rSR:.0f}')
            self.slider1.setMaximum(int(self.disp.slider1range*self.rSR))
            self.slider1.setValue(0)
            self.slider1.setSingleStep(ceil(self.rSR)) # 1 sec
            self.slider1.setPageStep(ceil(10*self.rSR)) #10 sec
            self.slider1.setTickInterval(ceil(10*self.rSR))
            self.text_slider1.setText(f'{self.slider1.value()/self.rSR:.0f}')

            self.slider0v2p = self.slider0.value() #for @update_plot, @slider0_Callback
            self.slider1v2p = self.slider1.value() #for @update_plot, @slider1_Callback
            #TODO - translate below
            # set(handles.xlim1,'String','0');
            # set(handles.xlim2,'String','0');
            self.setWindowTitle(self.shell)
            # set(Cap7_gh.NotePad.figure1,'Name',handles.version.Shell);
            self.deleteLabel()
            # set(handles.group_stop(1,:),'Enable','off');
            # set(handles.group_start(1,:),'Enable','on');
            self.Start_Stop.setText('Waiting')
            self.Start_Stop.setStyleSheet('color:rgb(225,135,0)')

            #adjust AO property
            if self.daq.ao.isrunning:
                self.daq.ao.stop()
            
            self.daq.ao.stop() #might be started again @resume
            time.sleep(0.003)
            if (self.algorithm >= 2) and (self.menuindex[0] == 0): #SQA but PSD context menu
                self.MenuSwitcher(1) #SQA context menu
            elif (self.algorithm == 1) and (self.menuindex[0] == 1): #PSD but SQA context menu
                self.MenuSwitcher(0) #PSD context menu
            #TODO - translate below
            # if strcmpi(get(handles.context_TTL,'Checked'),'off')
            #     set(handles.ao,'TriggerType','Immediate');
            # else
            #     set(handles.ao,'TriggerType','HwDigital');
            #     set(handles.ao,'HwDigitalTriggerSource','PFI0');
            #     %set(handles.ao,'TriggerFcn',{@AIwaiting,gcf});
            # end
            
            #self.daq.ai.start()
            self.Set_PSD_Callback() #this will start both AI and AO

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

            if self.slider0.value() == 0:
                self.xlim0.setText('0')
                self.xlim1.setText('0')
                self.Show_update_Callback() #force update because extra data may have been acquired after the last plot update
                self.slider0.blockSignals(True)
                self.slider0.setMaximum(0) #this makes the slider unmovable
                self.slider0.setValue(0)
                self.slider0.blockSignals(False)
            else:
                I,_ = self.plot0.getOriginalDataset()
                I = I.size
                self.slider0.setMaximum(self.aitime.size - I)
                self.slider0.setValue(self.aitime.size - I)
                self.slider0.setSingleStep(ceil(0.1*I))
                self.slider0.setPageStep(ceil(0.8*I))

            if self.slider1.value() == 0:
                #unlike slider0, extra data points are ignored as they are available from the upper panels already 
                self.slider1.setMaximum(0) #this makes the slider unmovable
            else:
                I,_ = self.plot2.getOriginalDataset()
                I = I.size
                self.slider1.setMaximum(self.aitime.size - I)
                self.slider1.setValue(self.aitime.size - I)
                self.slider1.setSingleStep(ceil(0.1*I))
                self.slider1.setPageStep(ceil(0.8*I))

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
            self.changed = True
            self.ChangedOrSaved()
            # %assignin('base','aodata',handles.aodata);
            if self.aidata.size == 0:
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
        if (not self.Start_Stop.isChecked()) and (len(self.aitime) != 0):
            self.Show_update_Callback()

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
        if (not self.Start_Stop.isChecked()) and (len(self.aitime) != 0):
            self.Show_update_Callback()

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

    def slider_Callback(self,V):
        if self.aitime.size == 0:
            return #this happens when resetting slider value in Start_Stop_Callback
        
        #V = self.sender().value() #int, in points
        slideridx = int(self.sender().objectName()[-1])
        if slideridx == 0: #slider0
            self.slider0v2p = V
            self.text_slider0.setText(f'{V/self.rSR:.0f}')
        else: #slider1
            self.slider1v2p = V
            self.text_slider1.setText(f'{V/self.rSR:.0f}')
        #Note - Page change won't emit sliderReleased() signal. i.e. cannot put disp update code in the corresponding callback
        if not self.daq.ai.isrunning:
            if slideridx == 0: #slider0
                data,_ = self.plot0.getOriginalDataset()
            else: #slider1
                data,_ = self.plot2.getOriginalDataset()
        
            I = data.size #in pt
            
            XData = self.aitime[V:V+I]
            if self.applyKseal:
                raise NotImplementedError
                #YTarget = self.aidata2 #Kseal adjusted data
            else:
                YTarget = self.aidata; #original data
            
            # def processYdata(ydata,fcheck):
            #     '''
            #     this nested function slices and filters data
            #     '''
            #     ydata = ydata[V:V+I]
            #     if fcheck:
            #         ydata += 0 # +0 forces Python to make a hard copy of the data
            #         self.lib.Dfilter2(self.fswitch,ydata.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            #                         self.fwindow,0,ydata.size,
            #                         ydata.ctypes.data_as(ctypes.POINTER(ctypes.c_double))) #modify in place
            #     return ydata

            # if not slideridx: #slider0
            #     if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[1] == 'p'):
            #         YData0 = processYdata(self.PSDofSQA[self.disp.dispindex[0]],self.fcheck[f'mf{self.disp.dispindex[0]}'])
            #     else:
            #         YData0 = processYdata(YTarget[self.disp.dispindex[0]],self.fcheck[f'mf{self.disp.dispindex[0]}'])
            #     if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[2] == 'p'):
            #         YData1 = processYdata(self.PSDofSQA[self.disp.dispindex[1]],self.fcheck[f'mf{self.disp.dispindex[1]}'])
            #     else:
            #         YData1 = processYdata(YTarget[self.disp.dispindex[1]],self.fcheck[f'mf{self.disp.dispindex[1]}'])
            #     self.plot0.setData(XData,YData0)
            #     self.plot1.setData(XData,YData1)
            #     self.xlim(self.axes0,(XData[0],XData[-1]))
            #     self.xlim(self.axes1,(XData[0],XData[-1]))
            #     if self.Lock.isChecked():
            #         lim1 = self.ylim(self.axes0,'range')
            #         D = (lim1[1]-lim1[0])/2
            #         M = (max(YData1)+min(YData1))/2
            #         self.ylim(self.axes1,((M-D),(M+D)))
            # else: #slider1
            #     if (self.disp.dispindex[2] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[3] == 'p'):
            #         YData2 = processYdata(self.PSDofSQA[self.disp.dispindex[2]],self.fcheck[f'mf{self.disp.dispindex[2]}'])
            #     else:
            #         YData2 = processYdata(YTarget[self.disp.dispindex[2]],self.fcheck[f'mf{self.disp.dispindex[2]}'])
            #     self.plot2.setData(XData,YData2)
            #     self.xlim(self.axes2,(XData[0],XData[-1]))

            if not slideridx: #slider0
                if (self.disp.dispindex[0] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[1] == 'p'):
                    YData0 = self.PSDofSQA[self.disp.dispindex[0],V:V+I]
                else:
                    YData0 = YTarget[self.disp.dispindex[0],V:V+I]
                if (self.disp.dispindex[1] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[2] == 'p'):
                    YData1 = self.PSDofSQA[self.disp.dispindex[1],V:V+I]
                else:
                    YData1 = YTarget[self.disp.dispindex[1],V:V+I]
                self.refresh_plot(XData,YData0,YData1,[],[])
            else: #slider1
                if (self.disp.dispindex[2] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[3] == 'p'):
                    YData2 = self.PSDofSQA[self.disp.dispindex[2],V:V+I]
                else:
                    YData2 = YTarget[self.disp.dispindex[2],V:V+I]
                self.refresh_plot([],[],[],XData,YData2)

    def LabelButton_Callback(self):
        if self.Start_Stop.isChecked():
            idx = int(self.sender().objectName()[-1]) #which button
            X = self.aitime[-1]
            Y = self.aidata[:,-1]
            S = eval(f'self.label_{idx}.text()')
            #text = pg.TextItem(f'\u2191\n{S}',color = 'k') #with upward arrow
            def dojob(ax,X,Y,S):
                #Note - exec is executing in a separate scope and does not have access to vars outside of this nested function (chatGPT)
                self.addLabel(ax,X,Y,S)
                if len(self.labelindex) != 0:
                    self.labelindex.append([self.disp.dispindex[int(ax.objectName()[-1])],X,Y,S])
                    #exec(f'self.labelindex.append([self.disp.dispindex[{axid}],X,Y,S])')
                else:
                    self.labelindex = [[self.disp.dispindex[int(ax.objectName()[-1])],X,Y,S]]
                    #exec(f'self.labelindex = [[self.disp.dispindex[{axid}],X,Y,S]]')

            if (1<=idx<=5): #left-hand set of buttons
                dojob(self.axes0,X,Y,S) #tag upper panel
            else: #right-hand set of buttons
                dojob(self.axes1,X,Y,S) #tag middle panel

    def Show_to_Callback(self):
        self.gh.crosshair = self.crosshair(self.axes0)
    
        #TODO - paused - 2/26/2025
        
        self.axes0.scene().sigMouseClicked.connect(lambda event: self.mouseInput(self.axes0,event))

    def makeFig_Callback(self):
        '''
        Correspond to the Show_Callback in Capmeter7 (MATLAB)
        '''
        Xdata, Ydata0 = self.plot0.getOriginalDataset()
        _,Ydata1 = self.plot1.getOriginalDataset()
        color0 = tuple([n/255 for n in self.disp.chcolor[self.disp.dispindex[0]]]) 
        color1 = tuple([n/255 for n in self.disp.chcolor[self.disp.dispindex[1]]])

        _, ax1 = plt.subplots() #returns fig and axis

        ax0 = ax1.twinx()  # Create a second y-axis sharing the same x-axis
        ax1.plot(Xdata,Ydata1,color=color1) #plot ax1 behind ax0
        ax0.plot(Xdata,Ydata0,color=color0)
        #move upper panel axis to the left and lower to the right
        ax0.yaxis.tick_left()
        ax0.yaxis.set_label_position('left')
        ax1.yaxis.tick_right()
        ax1.yaxis.set_label_position('right')
        ax1.set_xlabel("Time (s)")
        ax0.set_ylabel(f'Channel {self.disp.dispindex[0]}', color=color0)
        ax1.set_ylabel(f'Channel {self.disp.dispindex[1]}', color=color1)

        for capax, ax in zip([self.axes0, self.axes1],[ax0,ax1]):
            for item in capax.items():
                # Retrieve all text labels (pyqtgraph)
                if isinstance(item, pg.TextItem):
                    text = item.toPlainText()
                    pos = item.pos()
                    #print(f'{text}, x={pos.x()}, y={pos.y()}')
                    # Add labels to the figure
                    ax.annotate(text, pos,fontsize=12)
            
            xlim = self.xlim(capax,'range')
            ax.set_xlim(*xlim) #set_xlim(left, right)
            ylim = self.ylim(capax,'range')
            ax.set_ylim(*ylim) #set_ylim(bottom, top)

        plt.show() # without it, no fig will be shown
        #self.showDataTable(np.vstack((Xdata,Ydata0,Ydata1)))


    def toClipboard_Callback(self):
        Xdata, Ydata0 = self.plot0.getOriginalDataset()
        _,Ydata1 = self.plot1.getOriginalDataset()
        df = pd.DataFrame(np.vstack((Xdata,Ydata0,Ydata1)))
        df = df.T # same as df.transpose(); make it time-by-channel
        df_str = df.to_csv(sep='\t', index=False, header=False)
        clipboard = QApplication.clipboard()
        clipboard.setText(df_str)

    def Std_get_Callback(self):
        raise NotImplementedError
    
    def Std_scale_Callback(self):
        raise NotImplementedError
    
    def Set_PSD_Callback(self,algoChange = False):
        if not self.Start_Stop.isChecked():
            return #only continue if the program is running

        PSDfreq = abs(float(self.PSD_freq.text()))
        PSDamp = abs(float(self.PSD_amp.text()))
        if self.algorithm >= 2: #SQA
            if PSDfreq > 2.5:
                PSDfreq = 2.5
            elif PSDfreq < 2*self.rSR/1000:
                PSDfreq = 2*self.rSR/1000

        if (PSDfreq != self.PSDfreq) or (PSDamp != self.PSDamp) or (algoChange):
            self.aodata, PSDfreq, PSDamp = self.Wavecalc(PSDfreq,PSDamp)
            self.PSDfreq = PSDfreq
            self.PSDamp = PSDamp
            self.PSD_freq.setText(f'{self.PSDfreq:.2f}')
            self.PSD_amp.setText(f'{self.PSDamp:.2f}')
            #TODO - translate below
            # if get(handles.Pulse,'Value')
            #     stop(handles.ao);
            # end
            self.daq.ai.stop()
            self.daq.ao.stop() #ao might be started again in @resume
            #TODO - translate below
            # if ~strcmpi(handles.ao.TriggerType,'Immediate') && (handles.ai.TriggersExecuted ~= 0)
            #     set(handles.ao,'TriggerType','Immediate');
            # end
            # %assignin('base','aodata',handles.aodata);
            self.daq.ao.putdata(self.aodata)
            self.Set_filter_Callback() #adjust filter setting accordingly
            self.daq.ai.start()
            self.daq.ao.start()
            #TODO - need to re-sync AI and AO - verify it
           
        self.PSDphase = float(self.PSD_phase.text())
        P = abs(self.PSDphase)
        if P > 360:
            self.PSDphase = np.sign(self.PSDphase)*(P%360)
        if self.PSDphase > 180:
            self.PSDphase = self.PSDphase-360
        elif self.PSDphase < -180:
            self.PSDphase = self.PSDphase+360
        #self.PSD_phase.setText(f'{self.PSDphase:.2f}') #text will be updated by PSD_slider_callack
        self.PSD_slider.setValue(round(100*self.PSDphase)) #slider range is -18000 to 18000, int only

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
        raise NotImplementedError
    
    def PSDadd90_Callback(self):
        if self.daq.ai.isrunning:
            self.PSD_phase.setText(f'{self.PSDphase + 90:.2f}')
            self.Set_PSD_Callback()
        else:
            self.Phase_Shift.setText(f'{self.shiftvalue + 90:.2f}')
            self.PhaseShift_Callback()

    def AutoPhase_Callback(self):
        raise NotImplementedError

    def PSD_slider_Callback(self):
        '''
        this is a valueChanged callback, for updating PSD_phase text only
        sliderReleased signal is connected to Set_PSD_Callback directly
        '''
        self.PSD_phase.setText(f'{self.sender().value()/100:.2f}') #slider range is +/- 18000
        # if self.daq.ai.isrunning:
        #     self.Set_PSD_Callback()

    def Cm_Callback(self,index):
        '''
        index 0:Hardware, 1:PSD, 2:I-SQA, 3:Q-SQA
        '''
        if (self.algorithm != index):
            # prohibit transition from Hardware and PSD to any other algorithms or vice versa during acquisition
            # if (self.algorithm <= 1) and (self.Start_Stop.isChecked()): # hardware or PSD to others
            #     self.Cm.setCurrentIndex(self.algorithm)
            #     return
            # elif (index <= 1) and (self.algorithm >= 2) and (self.Start_Stop.isChecked()): # SQA to hardware or PSD
            #     self.Cm.setCurrentIndex(self.algorithm)
            #     return
            if (((self.algorithm <= 1) and (self.Start_Stop.isChecked())) or 
                ((index <= 1) and (self.algorithm >= 2) and (self.Start_Stop.isChecked()))):
                self.Cm.setCurrentIndex(self.algorithm)
                return

            # if index == 1: #PSD
            #     self.MenuSwitcher(0)
            # elif index >= 2: #SQA
            #     self.MenuSwitcher(1)

            self.algorithm = index
            self.Set_PSD_Callback(algoChange = True)

        if not self.daq.ai.isrunning: #MATLAB experience: %run the following scrips when ai is running will cause error
            if self.algorithm > 1: #not PSD or Hardware
                self.Auto_FP.setChecked(True)
                self.autofp = True
                self.PSDamp = []
            else: #SQA
                self.Auto_FP.setChecked(False)
                self.autofp = False
                self.PSDamp = []

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

    def Save_Callback(self):
        file = self.uisavefile(initialdir=self.current_folder, initialfile='*.npy',filetypes=[('Python','*.npy'),('All','*.*')])
        if not file.anchor: #if not cannelled, it will be something like 'C:\'
            return
        self.savevar(file)
        self.setWindowTitle(f'{self.shell} {file.name}')
        self.current_folder = file.parent #<class 'pathlib.WindowsPath'>
        self.changed = False
        self.ChangedOrSaved()
    
    def Load_Callback(self):
        '''
        The loaded data is in class np.ndarray instead of dict. Need to use data.item() to change it back to dict.
        Ref: https://stackoverflow.com/questions/66230865/load-dictionary-from-np-load
        '''
        if self.changed:
            if not self.dlg_SaveData(): #canceled or no selection
                return
        file = self.uigetfile(initialdir=self.current_folder, initialfile='*.npy',filetypes=[('Python','*.npy'),('All','*.*')])
        if not file.anchor: #if not cannelled, it will be something like 'C:\'
            return
        
        self.deleteLabel()
        data = np.load(file,allow_pickle=True).item()
        self.current_folder = file.parent
        for key,value in data.items(): #assign variables
            if key not in ['DAQinfo','shell']: #shell shouldn't be overwritten
                setattr(self,key,value)

        #TODO - translate below
        # handles.rSR = 1/(handles.aitime(3,1)-handles.aitime(2,1));
        # handles.Stdfactor = []; %convert volt to fF
        # guidata(hObject,handles);

        # if isfield(loadedvar,'note') %TW141108
        #     set(Cap7_gh.NotePad.edit_note,'String',loadedvar.note);
        # else
        #     set(Cap7_gh.NotePad.edit_note,'String','');
        # end

        if self.menuindex[0] != (0 if (len(self.PSDofSQA) == 0) else 1): #use appropriate context menu
            self.MenuSwitcher(1-self.menuindex[0]) # 0->1, 1->0

        self.setWindowTitle(f'{self.shell} {file.name}')
        #TODO - translate below
        # set(handles.DeDrift,'Enable','on');

        # Show all points in top and middle panels upon loading
        self.xlim0.setText('0')
        self.xlim1.setText('0')

        # Show all points in the bottom panel upon loading
        self.plot2.setData(self.aitime,self.aidata[0]) #YData doesn't matter as it will be updated again in Show_update_Callback
        #self.slider1.blockSignals(True) #did not block signal so the slider text can be udpated
        self.slider1.setMaximum(0) #this makes the slider unmovable
        self.slider1.setValue(0)
        #self.slider1.blockSignals(False)
        #TODO - translate below
        # edit_Kseal_Callback(handles.edit_Kseal, eventdata, handles); %TW141015, will update the plot
        self.Show_update_Callback() #remove this call when edit_Kseal_Callback is implememted
        self.changed = False
        self.ChangedOrSaved()
    
    def Notepad_Callback(self):
        print('notepad not implemented')
        raise NotImplementedError
    
    def Setting_Callback(self):
        print('setting not implemented')
        raise NotImplementedError
    
    def Show_update_Callback(self):
        '''
        returnPressed Fcn of xlim0, xlim1 QLineEdit boxes
        Also called by various callbacks (e.g. context_axes_Callback etc) to update
         all three plots.
        '''
        L = self.aitime.size
        if L == 0:
            print('No data to be displayed')
            return
        lim0 = float(self.xlim0.text())
        lim1 = float(self.xlim1.text())
        index0 = [] #for bottom panel
        index1 = [] #for bottom panel
        if (lim0 == lim1) or (lim0 > lim1):
            self.xlim0.setText('0')
            self.xlim1.setText('0')
            lim0 = 0
            lim1 = 0
        XData2,_ = self.plot2.getOriginalDataset()
        if (XData2.size < 2) or (XData2[-1] > self.aitime[-1]):
            XData2 = self.aitime
            self.slider1.setValue(0)

        lim0,lim1,index0,index1 = self.indexLoc(self.aitime,[lim0,lim1,XData2[0],XData2[-1]])
        if (lim1 == lim0): #show all data if lim0 == lim1
            lim1 = L-1 #keep in mind that lim is zero-based
        D = self.fwindow
        XData01 = self.aitime[lim0:lim1+1]
        XData2 = self.aitime[index0:index1+1]
        if self.applyKseal:
            pass
            #TODO - translate below
            # YTarget = handles.aidata2; %Kseal adjusted data
            # assignin('base','Cm_new',handles.aidata2(:,1));
            # assignin('base','Gm_new',handles.aidata2(:,2));
            # assignin('base','Kseal',str2double(get(handles.edit_Kseal,'String'))); %TW141101
        else:
            YTarget = self.aidata #original data

        YData = [None]*3
        for n in range(3): #assign YData0-2
            if (self.disp.dispindex[n] <= 1) and (self.menuindex[0] == 1) and (self.menuindex[n+1] == 'p'): #Ch0/1 PSDofSQA
                if n == 2:
                    YData[2] = self.PSDofSQA[self.disp.dispindex[2],index0:index1+1]
                else:
                    YData[n] = self.PSDofSQA[self.disp.dispindex[n],lim0:lim1+1]
            else:
                if n == 2:
                    YData[2] = YTarget[self.disp.dispindex[2],index0:index1+1]
                else:
                    YData[n] = YTarget[self.disp.dispindex[n],lim0:lim1+1]
        
        self.refresh_plot(XData01,YData[0],YData[1],XData2,YData[2])

        #update slider0
        I = lim1-lim0+1
        self.slider0.blockSignals(True) #prevent slider valueChanged callback from calling self.refresh_plot again
        self.slider0.setMaximum(self.aitime.size - I)
        self.slider0.setValue(lim0)
        self.slider0.setSingleStep(ceil(0.1*I))
        self.slider0.setPageStep(ceil(0.8*I))
        self.slider0.blockSignals(False)

        # update labels - in case called from context_axes... when changing the display channel
        if len(self.labelindex) != 0:
            self.deleteLabel()
            for label in self.labelindex:
                if label[0] in self.disp.dispindex[0:2]:
                    ax = eval(f'self.axes{label[0]}')
                    self.addLabel(ax,*label[1:]) # '*' unpacks the labelindex to indivirual arg
    
    def showDataTable(self,data,title='Figdata'):
        '''
        show data in QTableWidget
        2/26/2025: Not in use for now
        '''
        pass
        # # Create the main window
        # self.gh.dataTable = QWidget()
        # self.gh.dataTable.setWindowTitle(title)
        # layout = QVBoxLayout()

        # # Create a QTableWidget
        # table_widget = QTableWidget()
        # table_widget.setRowCount(data.shape[0])
        # table_widget.setColumnCount(data.shape[1])
        # #table_widget.setVerticalHeaderLabels(row_headers)

        # # Populate the table with data
        # for row in range(data.shape[0]):
        #     for col in range(data.shape[1]):
        #         item = QTableWidgetItem(str(data[row, col]))
        #         table_widget.setItem(row, col, item)

        # # Set selection mode and behavior
        # table_widget.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        # table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)

        # # Allow copying with default shortcuts like Ctrl+C
        # table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # # Enable copying
        # copy_action = QAction("Copy", table_widget)
        # copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        # copy_action.triggered.connect(lambda: copySelectedCells(table_widget))
        # table_widget.addAction(copy_action)

        # def copySelectedCells(table_widget):
        #     # Get the selected ranges
        #     selection = table_widget.selectedRanges()
        #     if selection:
        #         range_ = selection[0]
        #         rows = range(range_.topRow(), range_.bottomRow() + 1)
        #         cols = range(range_.leftColumn(), range_.rightColumn() + 1)

        #         # Construct the data to be copied
        #         data = "\n".join(
        #             "\t".join(table_widget.item(row, col).text() if table_widget.item(row, col) else ""
        #                     for col in cols)
        #             for row in rows
        #         )

        #         # Copy to clipboard
        #         clipboard = QApplication.clipboard()
        #         clipboard.setText(data)

        # # Add the table to the layout
        # layout.addWidget(table_widget)
        # self.gh.dataTable.setLayout(layout)

        # # Show the window
        # self.gh.dataTable.show()
        # #add closeRequestFcn?

    def closeEvent(self, a0):
        #print('closeEvent called')
        if self.Start_Stop.isChecked():
            self.Start_Stop.setChecked(False)
            self.Start_Stop_Callback()
        
        if self.daq.ai.isrunning: #should not be needed. added to be safe anyway.
            self.daq.ai.stop() 

        if self.daq.ao.isrunning:
            self.daq.ao.stop()
            self.daq.ao.putvalue([0,0])
        
        if self.changed:
            self.dlg_SaveData()
        #TODO - translate
        # delete(Cap7_gh.LoadedGUI);
        return super().closeEvent(a0)
    

#%% -------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
