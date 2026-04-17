package org.fog.test.perfeval;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.LinkedList;
import java.util.List;

import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Log;
import org.cloudbus.cloudsim.Pe;
import org.cloudbus.cloudsim.Storage;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.power.PowerHost;
import org.cloudbus.cloudsim.provisioners.RamProvisionerSimple;
import org.cloudbus.cloudsim.sdn.overbooking.BwProvisionerOverbooking;
import org.cloudbus.cloudsim.sdn.overbooking.PeProvisionerOverbooking;
import org.fog.application.AppEdge;
import org.fog.application.AppLoop;
import org.fog.application.Application;
import org.fog.application.selectivity.FractionalSelectivity;
import org.fog.entities.Actuator;
import org.fog.entities.FogBroker;
import org.fog.entities.FogDevice;
import org.fog.entities.FogDeviceCharacteristics;
import org.fog.entities.Sensor;
import org.fog.entities.Tuple;
import org.fog.placement.Controller;
import org.fog.placement.ModuleMapping;
import org.fog.placement.ModulePlacementEdgewards;
import org.fog.policy.AppModuleAllocationPolicy;
import org.fog.scheduler.StreamOperatorScheduler;
import org.fog.utils.FogLinearPowerModel;
import org.fog.utils.FogUtils;
import org.fog.utils.TimeKeeper;
import org.fog.utils.distribution.DeterministicDistribution;

public class FloodMonitoringSimulation {

    static List<FogDevice> fogDevices = new ArrayList<>();
    static List<Sensor> sensors = new ArrayList<>();
    static List<Actuator> actuators = new ArrayList<>();
    static double SENSOR_TRANSMISSION_TIME = 4.5;

    public static void main(String[] args) {
        Log.printLine("Starting Flood Monitoring Simulation...");
        try {
            Log.disable();
            int num_user = 1;
            Calendar calendar = Calendar.getInstance();
            boolean trace_flag = false;
            CloudSim.init(num_user, calendar, trace_flag);

            String appId = "flood-monitoring";
            FogBroker broker = new FogBroker("broker");
            Application application = createApplication(appId, broker.getId());
            application.setUserId(broker.getId());

            createFogDevices(broker.getId(), appId);

            Controller controller = new Controller("flood-controller", fogDevices, sensors, actuators);
            ModuleMapping moduleMapping = ModuleMapping.createModuleMapping();
            moduleMapping.addModuleToDevice("sensorModule", "edge-device");
            moduleMapping.addModuleToDevice("processingModule", "fog-node");
            moduleMapping.addModuleToDevice("cloudModule", "cloud");

            controller.submitApplication(application, new ModulePlacementEdgewards(fogDevices, sensors, actuators, application, moduleMapping));

            TimeKeeper.getInstance().setSimulationStartTime(Calendar.getInstance().getTimeInMillis());

            CloudSim.startSimulation();
            CloudSim.stopSimulation();
            Log.printLine("Simulation finished!");
        } catch (Exception e) {
            e.printStackTrace();
            Log.printLine("Unwanted errors happened");
        }
    }

    private static void createFogDevices(int userId, String appId) {
        FogDevice cloud = createFogDevice("cloud", 18000, 36000, 25000, 25000, 0, 0.01, 200, 150);
        cloud.setParentId(-1);
        cloud.setUplinkLatency(90);
        fogDevices.add(cloud);

        FogDevice fogNode = createFogDevice("fog-node", 9000, 18000, 4500, 4500, 1, 0.0, 120.5, 90.5);
        fogNode.setParentId(cloud.getId());
        fogNode.setUplinkLatency(12);
        fogDevices.add(fogNode);

        FogDevice edgeDevice = createFogDevice("edge-device", 3500, 7000, 2500, 2500, 2, 0.0, 100.0, 85.0);
        edgeDevice.setParentId(fogNode.getId());
        edgeDevice.setUplinkLatency(6);
        fogDevices.add(edgeDevice);

        addSensorsAndActuators(edgeDevice.getId(), userId, appId);
    }

    private static void addSensorsAndActuators(int parentId, int userId, String appId) {
        sensors.add(new Sensor("s-water-level", "WATER_LEVEL", userId, appId, new DeterministicDistribution(SENSOR_TRANSMISSION_TIME)));
        sensors.add(new Sensor("s-rainfall", "RAINFALL", userId, appId, new DeterministicDistribution(SENSOR_TRANSMISSION_TIME)));
        sensors.add(new Sensor("s-flow-rate", "FLOW_RATE", userId, appId, new DeterministicDistribution(SENSOR_TRANSMISSION_TIME)));
        sensors.add(new Sensor("s-soil-moisture", "SOIL_MOISTURE", userId, appId, new DeterministicDistribution(SENSOR_TRANSMISSION_TIME)));
        sensors.add(new Sensor("s-temperature", "TEMPERATURE", userId, appId, new DeterministicDistribution(SENSOR_TRANSMISSION_TIME)));

        for (Sensor s : sensors) {
            s.setGatewayDeviceId(parentId);
            s.setLatency(0.8);
        }

        Actuator floodAlert = new Actuator("a-flood-alert", userId, appId, "FLOOD_ALERT");
        floodAlert.setGatewayDeviceId(parentId);
        floodAlert.setLatency(1.0);
        actuators.add(floodAlert);
    }

    private static FogDevice createFogDevice(String nodeName, long mips, int ram, long upBw, long downBw,
                                             int level, double ratePerMips, double busyPower, double idlePower) {
        List<Pe> peList = new ArrayList<>();
        peList.add(new Pe(0, new PeProvisionerOverbooking(mips)));

        int hostId = FogUtils.generateEntityId();
        long storage = 500000;
        int bw = 15000;

        PowerHost host = new PowerHost(
                hostId,
                new RamProvisionerSimple(ram),
                new BwProvisionerOverbooking(bw),
                storage,
                peList,
                new StreamOperatorScheduler(peList),
                new FogLinearPowerModel(busyPower, idlePower)
        );

        List<Host> hostList = new ArrayList<>();
        hostList.add(host);

        LinkedList<Storage> storageList = new LinkedList<>();
        FogDeviceCharacteristics characteristics = new FogDeviceCharacteristics(
                "x86", "Linux", "Xen", host, 10.0, 3.0, 0.05, 0.001, 0.0);

        FogDevice device = null;
        try {
            device = new FogDevice(nodeName, characteristics, new AppModuleAllocationPolicy(hostList), storageList, 10, upBw, downBw, 0, ratePerMips);
        } catch (Exception e) {
            e.printStackTrace();
        }

        device.setLevel(level);
        return device;
    }

    private static Application createApplication(String appId, int userId) {
        Application application = Application.createApplication(appId, userId);

        application.addAppModule("sensorModule", 12);
        application.addAppModule("processingModule", 15);
        application.addAppModule("cloudModule", 20);

        String[] sensorTypes = { "WATER_LEVEL", "RAINFALL", "FLOW_RATE", "SOIL_MOISTURE", "TEMPERATURE" };
        for (String sensor : sensorTypes) {
            application.addAppEdge(sensor, "sensorModule", 1500, 800, sensor, Tuple.UP, AppEdge.SENSOR);
            application.addTupleMapping("sensorModule", sensor, "_SENSOR_TO_PROCESSING_", new FractionalSelectivity(1.0));
        }

        application.addAppEdge("sensorModule", "processingModule", 2500, 900, "_SENSOR_TO_PROCESSING_", Tuple.UP, AppEdge.MODULE);
        application.addAppEdge("processingModule", "cloudModule", 2500, 900, "_PROCESSING_TO_CLOUD_", Tuple.UP, AppEdge.MODULE);
        application.addAppEdge("cloudModule", "FLOOD_ALERT", 1000, 500, "FLOOD_ALERT", Tuple.DOWN, AppEdge.ACTUATOR);

        application.addTupleMapping("processingModule", "_SENSOR_TO_PROCESSING_", "_PROCESSING_TO_CLOUD_", new FractionalSelectivity(1.0));
        application.addTupleMapping("cloudModule", "_PROCESSING_TO_CLOUD_", "FLOOD_ALERT", new FractionalSelectivity(1.0));

        AppLoop loop = new AppLoop(new ArrayList<String>() {{
            add("WATER_LEVEL");
            add("sensorModule");
            add("processingModule");
            add("cloudModule");
            add("FLOOD_ALERT");
        }});

        application.setLoops(new ArrayList<AppLoop>() {{ add(loop); }});
        return application;
    }
}
