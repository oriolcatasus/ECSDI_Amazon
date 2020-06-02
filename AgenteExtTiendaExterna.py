# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request, render_template

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants


# Configuration stuff
hostname = '127.0.1.1'
port = 9010

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExtTiendaExterna = Agent('AgenteExtTiendaExterna',
                       agn.AgenteExtTiendaExterna,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/", methods=['GET', 'POST'])
def comunicacion():
    if request.method == 'GET':
        return render_template('vendedor_externo.html')

    global mss_cnt
  
    message = Graph()
    mss_cnt = mss_cnt + 1
    peticion = agn['enviar_peticion_' + str(mss_cnt)]
    message.add((peticion, RDF.type, Literal('Enviar_Peticion')))
    message.add((peticion, agn.nombre_tienda, Literal((request.form['nombre_tienda']))))
    message.add((peticion, agn.nombre, Literal((request.form['nombre_producto']))))
    message.add((peticion, agn.precio, Literal(int(request.form['precio_producto']))))
    message.add((peticion, agn.peso, Literal(int(request.form['peso_producto']))))
    message.add((peticion, agn.tieneMarca, Literal(request.form['marca'].lower())))
    message.add((peticion, agn.tipo, Literal(request.form['tipo'].lower())))
    message.add((peticion, agn.cuenta_bancaria, Literal(int(request.form['cuenta_bancaria']))))    
    comunicadorExterno = AgenteExtTiendaExterna.directory_search(DirectoryAgent, agn.ComunicadorExterno)    
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgenteExtTiendaExterna.uri,
        receiver=comunicadorExterno.uri,
        msgcnt=mss_cnt,
        content=peticion
    )
    logging.info("Arriba")
    respuesta_peticion = ""
    response = send_message(msg, comunicadorExterno.address)
    for item in response.subjects(RDF.type, Literal('RespuestaPeticion')):
        for RespuestaPeticion in response.objects(item, agn.respuesta_peticion):
            respuesta_peticion= str(RespuestaPeticion)
            logging.info(respuesta_peticion)
    return render_template('vendedor_externo.html', respuesta=respuesta_peticion)


@app.route("/comm")
def comm():    
    req = Graph().parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']    
    nombreProd = req.value(content, agn.nombre_prod)
    peso = req.value(content, agn.peso)
    cp = req.value(content, agn.cp)
    direccion = req.value(content, agn.direccion)
    prioridad_envio = req.value(content, agn.prioridad_envio)
    prioridad = ""
    if(int(prioridad_envio) > 0):
        prioridad = "con prioridad"
    else: 
        prioridad = "sin prioridad"
    logging.info("Se ha de hacer el envio " + prioridad + " del producto " + str(nombreProd) + 
                ", con un peso de " + str(peso) + "g, a la dirección " + str(direccion) +
                " con codigo postal " + str(cp))
    return Graph().serialize(format='xml')


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AgenteExtTiendaExterna.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')