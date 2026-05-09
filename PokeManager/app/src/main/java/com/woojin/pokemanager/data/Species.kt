package com.woojin.pokemanager.data

data class Species(
    val id: String,
    val name: String,
    val nameKo: String,
    val dex: Int,
    val atk: Int,
    val def: Int,
    val sta: Int,
    val types: List<String>
)
